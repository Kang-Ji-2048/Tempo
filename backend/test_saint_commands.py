import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_auth_helpers import auth_headers
import saint_commands as saint

FIXED=datetime(2026,10,25,12,tzinfo=timezone.utc)
# Each phrasing has an expected action/constraint or an explicit clarification.
EVALS=[
 ('book me a court Saturday morning','book_court',True),
 ('find a court Saturday morning','search_venues',True),
 ("something indoor Saturday, I'm not risking rain",'search_venues',True),
 ('reserve an outdoor tennis court tomorrow at 7pm','book_court',False),
 ('show badminton courts Monday evening','search_venues',True),
 ('search for tennis courts Tuesday afternoon','search_venues',True),
 ('book badminton Wednesday at 10:30 for 30 minutes','book_court',True),
 ('reserve a court Thursday at 9am for 90 minutes','book_court',True),
 ('book a tennis court Friday evening for 1 hour','book_court',True),
 ("don't book a court, find one Saturday morning",'search_venues',True),
 ('book a court this weekend',None,None),
 ('book a court',None,None),
 ('book Saturday or Sunday',None,None),
 ('book an indoor outdoor court Saturday',None,None),
 ('book squash Saturday',None,None),
 ('book the cheapest court Saturday',None,None),
 ('book a court Saturday under £20',None,None),
 ('cancel my booking',None,None),
 ('invite my partner',None,None),
 ('book Saturday at 25:00',None,None),
]

class SaintTests(unittest.TestCase):
 def setUp(self):
  saint._MEMORY.clear()
  self.db=patch.object(saint.db_mongo,'get_db',return_value=None);self.db.start();self.addCleanup(self.db.stop)
  self.clock=patch.object(saint,'now',return_value=FIXED);self.clock.start();self.addCleanup(self.clock.stop)
  app=FastAPI();app.include_router(saint.router)
  self.client=TestClient(app,headers=auth_headers('alice','player'))
  self.prefs=saint.Preferences(home_area='Camden')
  self.client.put('/api/v1/saint/preferences/alice',json=self.prefs.model_dump())
 def proposal(self):
  return self.client.post('/command',json={'user':'alice','text':'book an indoor court Saturday morning'}).json()['proposal']
 def test_twenty_phrasings(self):
  for phrase,expected,indoor in EVALS:
   with self.subTest(phrase=phrase):
    result=saint.plan('alice',phrase,self.prefs)
    if expected is None:self.assertEqual(result['kind'],'question')
    else:
     self.assertEqual(result['proposal']['action']['type'],expected)
     # Unspecified indoor preference chooses the indoor mock venue without claiming a constraint.
     self.assertEqual(result['proposal']['action']['params']['venue_id'],'mock-outdoor' if indoor is False else 'mock-indoor')
 def test_planning_does_not_write_or_book(self):
  before=copy.deepcopy(saint._MEMORY)
  with patch.object(saint,'put_record',side_effect=AssertionError('write')),patch.object(saint.ADAPTER,'book') as book,patch.object(saint.ADAPTER,'search') as search:
   self.assertEqual(self.client.post('/command',json={'user':'alice','text':'book Saturday morning'}).json()['kind'],'proposal')
   book.assert_not_called();search.assert_not_called()
  self.assertEqual(before,saint._MEMORY)
 def test_approval_is_logged_and_idempotent(self):
  proposal=self.proposal();body={'proposal':proposal,'approved':True}
  with patch.object(saint.ADAPTER,'book',wraps=saint.ADAPTER.book) as book:
   first=self.client.post('/api/v1/saint/actions/decision',json=body)
   second=self.client.post('/api/v1/saint/actions/decision',json=body)
  self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json(),second.json())
  self.assertEqual(first.json()['status'],'executed_mock');book.assert_called_once()
  self.assertTrue(first.json()['result']['demo'])
 def test_decline_never_calls_provider(self):
  proposal=self.proposal()
  with patch.object(saint.ADAPTER,'book') as book:
   response=self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':False})
   book.assert_not_called()
  self.assertEqual(response.json()['status'],'declined')
  self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,409)
 def test_modified_proposal_rejected(self):
  proposal=self.proposal();proposal['action']['params']['area']='Other area'
  self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,400)
 def test_expiry(self):
  proposal=self.proposal()
  with patch.object(saint,'now',return_value=datetime(2026,10,25,13,tzinfo=timezone.utc)):
   self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,410)
 def test_ownership(self):
  proposal=self.proposal();bob=TestClient(self.client.app,headers=auth_headers('bob','player'))
  self.assertEqual(bob.post('/command',json={'user':'alice','text':'book Saturday'}).status_code,403)
  self.assertEqual(bob.put('/api/v1/saint/preferences/alice',json=self.prefs.model_dump()).status_code,403)
  self.assertEqual(bob.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,403)
 def test_missing_preferences_clarifies(self):
  self.assertEqual(saint.plan('bob','book Saturday',saint.Preferences())['kind'],'question')
 def test_provider_failure_not_retried(self):
  body=saint.Decision(proposal=self.proposal(),approved=True)
  with patch.object(saint.ADAPTER,'book',side_effect=TimeoutError) as book:
   self.assertEqual(saint.execute(body)['status'],'needs_review');saint.execute(body);book.assert_called_once()
 def test_parallel_approvals_call_provider_once(self):
  body=saint.Decision(proposal=self.proposal(),approved=True)
  with patch.object(saint.ADAPTER,'book',wraps=saint.ADAPTER.book) as book:
   with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(lambda _:saint.execute(body),range(20)))
   book.assert_called_once()
 def test_search_approval_uses_search_only(self):
  proposal=saint.plan('alice','find Saturday morning',self.prefs)['proposal']
  with patch.object(saint.ADAPTER,'book') as book:
   result=saint.execute(saint.Decision(proposal=proposal,approved=True));book.assert_not_called()
  self.assertIn('venues',result['result'])
 def test_unknown_action_and_extra_fields_rejected(self):
  proposal=self.proposal();proposal['action']['type']='charge_card'
  self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,422)
 def test_approval_flag_cannot_be_removed(self):
  proposal=self.proposal();proposal['action']['requires_approval']=False
  self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True}).status_code,422)
 def test_status_requires_authentication_and_ownership(self):
  proposal=self.proposal();self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':False})
  url='/api/v1/saint/actions/'+proposal['action']['idempotency_key']
  self.assertEqual(TestClient(self.client.app).get(url).status_code,401)
  self.assertEqual(TestClient(self.client.app,headers=auth_headers('bob','player')).get(url).status_code,403)
 def test_negated_constraints_and_multiple_times_clarify(self):
  for text in ['book a court not outdoors Saturday','book Saturday at 9 or 10','book today or tomorrow']:
   self.assertEqual(saint.plan('alice',text,self.prefs)['kind'],'question')
 def test_mongo_write_failure_does_not_execute(self):
  body=saint.Decision(proposal=self.proposal(),approved=True)
  with patch.object(saint,'claim',side_effect=saint.HTTPException(503,'storage unavailable')),patch.object(saint.ADAPTER,'book') as book:
   with self.assertRaises(saint.HTTPException):saint.execute(body)
   book.assert_not_called()
 def test_saint_credential_relays_approval_for_its_player_only(self):
  proposal=self.proposal();relay=TestClient(self.client.app,headers=auth_headers('alice','saint'))
  self.assertEqual(relay.post('/command',json={'user':'bob','text':'book Saturday'}).status_code,403)
  response=relay.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True})
  self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['approved_via'],'saint_relay')
  self.assertEqual(self.client.post('/api/v1/saint/actions/decision',json={'proposal':self.proposal(),'approved':True}).json()['approved_via'],'player')
 def test_saint_credential_cannot_leave_saint_routes(self):
  from auth import install_auth
  app=FastAPI();install_auth(app);app.include_router(saint.router)
  @app.get('/api/v1/sessions')
  def sessions():return []
  relay=TestClient(app,headers=auth_headers('alice','saint'))
  self.assertEqual(relay.get('/api/v1/sessions').status_code,403)
  self.assertEqual(relay.get('/api/v1/saint/preferences/alice').status_code,200)
  self.assertEqual(TestClient(app,headers=auth_headers('alice','player')).get('/api/v1/sessions').status_code,200)

if __name__=='__main__':unittest.main()
