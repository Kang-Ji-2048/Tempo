import hashlib
import hmac
import os
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_auth_helpers import auth_headers
from auth import install_auth
import saint_commands as saint
import saint_events as events

FIXED=datetime(2026,10,25,12,tzinfo=timezone.utc)

class SaintEventTests(unittest.TestCase):
 def setUp(self):
  saint._MEMORY.clear()
  for name,value in (('SAINT_WEBHOOK_URL',''),('TEMPO_WEBHOOK_SECRET','')):
   env=patch.dict(os.environ,{name:value});env.start();self.addCleanup(env.stop)
  self.db=patch.object(saint.db_mongo,'get_db',return_value=None);self.db.start();self.addCleanup(self.db.stop)
  self.clock=patch.object(saint,'now',return_value=FIXED);self.clock.start();self.addCleanup(self.clock.stop)
  app=FastAPI();install_auth(app);app.include_router(saint.router);app.include_router(events.router)
  @app.get('/api/v1/sessions')
  def sessions():return []
  self.client=TestClient(app,headers=auth_headers('alice','player'))
  self.client.put('/api/v1/saint/preferences/alice',json=saint.Preferences(home_area='Camden',sport='tennis',preferred_time='18:30').model_dump())
 def test_slot_opened_carries_a_signed_proposal_and_is_logged(self):
  with patch.object(saint.ADAPTER,'book') as book,patch.object(saint.ADAPTER,'search') as search:
   result=self.client.post('/api/v1/saint/events/mock-slot-opened/alice').json()
   book.assert_not_called();search.assert_not_called()
  self.assertEqual(result['status'],'staged')
  proposal=result['event']['proposal']
  self.assertEqual(proposal['action']['type'],'book_court')
  self.assertEqual(proposal['action']['params']['starts_at'],'2026-10-31T10:00:00Z')
  self.assertEqual(saint._MEMORY['saint_event_log:'+result['event']['event_id']]['status'],'staged')
  # The attached proposal goes through the normal approval route unchanged.
  decided=self.client.post('/api/v1/saint/actions/decision',json={'proposal':proposal,'approved':True})
  self.assertEqual(decided.json()['status'],'executed_mock')
 def test_push_signs_the_exact_body(self):
  event=events.court_slot_opened('alice')
  with patch.dict(os.environ,{'SAINT_WEBHOOK_URL':'https://saint.example/hook','TEMPO_WEBHOOK_SECRET':'s'*32}),\
       patch.object(events.requests,'post') as post:
   post.return_value.ok=True;post.return_value.status_code=202
   self.assertEqual(events.push(event)['status'],'sent')
  sent=post.call_args.kwargs
  expected='sha256='+hmac.new(b's'*32,sent['data'],hashlib.sha256).hexdigest()
  self.assertEqual(sent['headers']['X-Tempo-Signature'],expected)
 def test_unreachable_saint_is_logged_as_failed(self):
  with patch.dict(os.environ,{'SAINT_WEBHOOK_URL':'https://saint.example/hook'}),\
       patch.object(events.requests,'post',side_effect=events.requests.ConnectionError):
   self.assertEqual(events.push(events.court_slot_opened('alice'))['status'],'failed')
 def test_argon_fail_proposes_a_court_and_pass_pushes_nothing(self):
  self.assertIsNone(events.argon_verdict('alice',{'verification_status':'PASS'}))
  event=events.argon_verdict('alice',{'verification_status':'FAIL','live_drill_prescription':'Shadow swings, high elbow.','right_elbow_contact_deg':152.0})
  params=event.proposal.action.params
  self.assertEqual((params.sport,params.starts_at.hour,params.starts_at.minute),('tennis',18,30))
  self.assertIn('Shadow swings',event.summary);self.assertEqual(event.data['right_elbow_contact_deg'],152.0)
 def test_without_preferences_the_event_carries_the_question(self):
  event=events.argon_verdict('bob',{'verification_status':'FAIL'})
  self.assertIsNone(event.proposal);self.assertIn('home area',event.data['question'])
 def test_mock_trigger_requires_ownership(self):
  bob=TestClient(self.client.app,headers=auth_headers('bob','player'))
  self.assertEqual(bob.post('/api/v1/saint/events/mock-slot-opened/alice').status_code,403)
 def test_tools_lists_only_saint_routes(self):
  relay=TestClient(self.client.app,headers=auth_headers('alice','saint'))
  paths=relay.get('/api/v1/saint/tools').json()['paths']
  self.assertIn('/command',paths);self.assertIn('/api/v1/saint/actions/decision',paths)
  self.assertNotIn('/api/v1/sessions',paths)

if __name__=='__main__':unittest.main()
