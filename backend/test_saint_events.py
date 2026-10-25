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
 def test_pass_after_fail_verifies_the_fix_once(self):
  events.argon_verdict('alice',{'verification_status':'FAIL','right_elbow_contact_deg':152.0,'threshold_deg':165.0})
  self.assertIsNone(events.argon_verdict('alice',{'verification_status':'NOT_MEASURED'}))
  event=events.argon_verdict('alice',{'verification_status':'PASS','right_elbow_contact_deg':167.4,'threshold_deg':165.0})
  self.assertEqual(event.type,'fix_verified');self.assertIsNone(event.proposal)
  self.assertEqual((event.data['before_deg'],event.data['after_deg']),(152.0,167.4))
  self.assertIn('152° to 167°',event.summary);self.assertIn('target 165°',event.summary)
  self.assertIsNone(events.argon_verdict('alice',{'verification_status':'PASS','right_elbow_contact_deg':168.0}))
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

 def test_argon_job_sender_pushes_a_signed_coaching_job(self):
  import agent_argon_saint as agent
  with patch.dict(os.environ,{'SAINT_WEBHOOK_URL':'https://saint.example/hook','TEMPO_WEBHOOK_SECRET':'s'*32}),\
       patch.object(events.requests,'post') as post:
   post.return_value.ok=True;post.return_value.status_code=202
   result=agent.dispatch_saint_webhook({'proactive_training_notification':'Re-film side-on.'},'SAINT_JOB_STAGED',{'user_name':'alice'})
  self.assertTrue(result['dispatched']);self.assertTrue(result['webhook_configured'])
  body=events.json.loads(post.call_args.kwargs['data'])
  self.assertEqual((body['type'],body['user'],body['summary'],body['data']['event_type']),('coaching_job','alice','Re-film side-on.','SAINT_JOB_STAGED'))
 def test_receipt_reads_event_fields(self):
  from api.v1 import omnichannel
  event=events.coaching_message('alice','PRE_SESSION_PRIMING','Warm up.','+447700900000','whatsapp')
  app=FastAPI();app.include_router(omnichannel.router)
  with patch.dict(os.environ,{'TEMPO_WEBHOOK_SECRET':'s'*32}),patch.object(omnichannel.db_mongo,'get_db',return_value=None),\
       patch.object(omnichannel.logger,'info') as log:
   ok=TestClient(app).post('/api/v1/webhooks/saint-delivery-receipt',json=event.model_dump(mode='json'),headers={'X-Tempo-Webhook-Secret':'s'*32})
  self.assertEqual(ok.status_code,200,ok.text)
  self.assertEqual(log.call_args.args[2:],('PRE_SESSION_PRIMING','alice','+447700900000'))
 def test_saint_pulls_undelivered_events_once(self):
  first=self.client.post('/api/v1/saint/events/mock-slot-opened/alice').json()['event']
  with patch.object(saint,'now',return_value=FIXED.replace(minute=5)):
   events.push(events.argon_verdict('alice',{'verification_status':'FAIL','right_elbow_contact_deg':150.0}))
  events.push(events.court_slot_opened('bob'))
  relay=TestClient(self.client.app,headers=auth_headers('alice','saint'))
  pulled=relay.get('/api/v1/saint/events/pending/alice').json()['events']
  self.assertEqual([e['type'] for e in pulled],['court_slot_opened','argon_verdict'])
  self.assertEqual(pulled[0]['event_id'],first['event_id'])
  self.assertEqual(relay.get('/api/v1/saint/events/pending/alice').json()['events'],[])
  self.assertEqual(saint._MEMORY['saint_event_log:'+first['event_id']]['status'],'pulled')
  # The pulled proposal still goes through the normal approval route.
  decided=relay.post('/api/v1/saint/actions/decision',json={'proposal':pulled[0]['proposal'],'approved':True})
  self.assertEqual(decided.json()['approved_via'],'saint_relay')
 def test_saint_cannot_pull_another_players_events(self):
  relay=TestClient(self.client.app,headers=auth_headers('alice','saint'))
  self.assertEqual(relay.get('/api/v1/saint/events/pending/bob').status_code,403)

if __name__=='__main__':unittest.main()
