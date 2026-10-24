import os
import unittest
from unittest.mock import patch
import agent_argon_saint as agent

class ModelValidationTests(unittest.TestCase):
    def run_agent(self):
        return agent.run_argon_and_saint_agent('alice', {'right_elbow_contact_deg':170}, {'heart_rate_bpm':140},
            {'player_name':'Illustrative profile', 'right_elbow_contact_deg':175})

    def test_invalid_provider_json_does_not_claim_live_model_success(self):
        with patch.object(agent, '_call_gemini_4_argon', return_value='{"ok":true}'):
            result = self.run_agent()
        self.assertEqual(result['model_status'], 'invalid_output')
        self.assertEqual(result['model'], 'deterministic-verified-fallback')

    def test_provider_failure_remains_visible(self):
        with patch.object(agent, '_call_gemini_4_argon', side_effect=RuntimeError('provider failure')):
            result = self.run_agent()
        self.assertEqual(result['model_status'], 'provider_error')

    def test_valid_provider_output_keeps_the_live_model_identity(self):
        import json
        output = {'verification_status':'FAIL', 'biomechanical_diagnosis':'Observed reach',
            'live_drill_prescription':'Practice comfortable reach', 'saint_agent_job':{
                'plain_english_instruction':'Stage practice', 'proactive_training_notification':'Practice',
                'requires_human_approval':False, 'approval_action_summary':'Approve practice'}}
        with patch.object(agent, '_call_gemini_4_argon', return_value=json.dumps(output)):
            result = self.run_agent()
        self.assertEqual(result['model_status'], 'live')
        self.assertNotEqual(result['model'], 'deterministic-verified-fallback')
        self.assertEqual(result['verification_status'], 'PASS')
        self.assertTrue(result['saint_agent_job']['requires_human_approval'])
        self.assertIn('unvalidated', result['biomechanical_diagnosis'])
