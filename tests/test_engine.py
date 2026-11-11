import json
import unittest
from pathlib import Path
from ln_agent import Case, Fact, Policy, Orchestrator, FixtureResearchTool
from ln_agent.evidence import evaluate
from ln_agent.extraction_contract import validate_extraction

BASE=Path(__file__).resolve().parents[1]
case_data=json.loads((BASE/'examples/demo_case.json').read_text(encoding='utf-8'))
research_data=json.loads((BASE/'examples/research_fixtures.json').read_text(encoding='utf-8'))

class TestDynamicAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=Case.from_dict(case_data)
        cls.report=Orchestrator(Policy(), FixtureResearchTool(research_data)).run(cls.case)
        cls.r={x['hit_id']: x for x in cls.report['results']}

    def test_dob_conflict_proposes_exclusion(self):
        self.assertEqual(self.r['H01_DOB_CONFLICT']['route'], 'EXCLUSION_CANDIDATE')
        self.assertTrue(self.r['H01_DOB_CONFLICT']['review_required'])
    def test_prebirth_action_excludes(self):
        self.assertIn('PRE_BIRTH_ACTION_IMPOSSIBLE', self.r['H02_TIME_IMPOSSIBLE']['reasons'])
    def test_exact_id_strong_link_not_auto_release(self):
        self.assertEqual(self.r['H03_DOCUMENT_MATCH']['route'], 'LINKED_RISK_REVIEW')
    def test_former_pep_is_not_identity_exclusion(self):
        x=self.r['H04_FORMER_PEP_UNRESOLVED']
        self.assertEqual(x['route'], 'RESIDUAL_SUSPICION')
        self.assertIn('former_pep', x['suspicion']['factors'])
    def test_investigate_then_stop(self):
        x=self.r['H05_INVESTIGATE_THEN_EXCLUDE']
        self.assertEqual(x['route'], 'EXCLUSION_CANDIDATE')
        self.assertEqual(len(x['actions']),1)
        self.assertGreaterEqual(len(x['history']),2)
    def test_unresolved_sanctions_mandatory_review(self):
        x=self.r['H06_SANCTIONS_NAME_ONLY']
        self.assertEqual(x['suspicion']['recommendation'],'MANDATORY_REVIEW')
    def test_phase_two_separate(self):
        self.assertIsNone(self.r['H01_DOB_CONFLICT']['suspicion'])
        self.assertGreaterEqual(self.r['H07_SUSPICIOUS_COINCIDENCE']['suspicion']['score'],7)
    def test_photo_difference_not_hard_rule(self):
        self.assertEqual(self.r['H08_PHOTO_DIFFERENCE']['route'],'RESIDUAL_SUSPICION')
        self.assertIn('photo_difference_human_only', self.r['H08_PHOTO_DIFFERENCE']['evidence']['soft_signals'])
    def test_company_registration_strong_link(self):
        self.assertEqual(self.r['H09_COMPANY_REG_MATCH']['route'],'LINKED_RISK_REVIEW')
    def test_shared_address_does_not_confirm_sanction(self):
        self.assertEqual(self.r['H10_ADDRESS_ONLY']['identity'],'unresolved')
    def test_later_counterevidence_overrides_early_dob_link(self):
        self.assertEqual(self.r['H11_DOB_MATCH_THEN_CONFLICT']['route'],'EVIDENCE_CONFLICT_REVIEW')
    def test_dob_with_name_still_only_strong_link(self):
        self.assertEqual(self.r['H12_DOB_MATCH_ONLY']['route'],'LINKED_RISK_REVIEW')
    def test_dob_alone_does_not_prove_identity(self):
        from ln_agent.models import Hit
        from ln_agent.router import DecisionRouter
        from ln_agent.tools import InvestigationAgent
        hit=Hit(hit_id='T-DOB',subject_id='p1',category='enforcement',facts=[
            Fact.from_dict(dict(side='hit',field='dob',value='1995-06-15',evidence_id='test:dob',origin='ln_structured',checked=True))
        ])
        x=DecisionRouter(Policy(),InvestigationAgent(FixtureResearchTool())).run_hit(self.case,hit)
        self.assertEqual(x.route,'RESIDUAL_SUSPICION')
    def test_no_cross_hit_photo_fact_leakage(self):
        self.assertNotIn('photo_difference_human_only',self.r['H07_SUSPICIOUS_COINCIDENCE']['evidence']['soft_signals'])
    def test_no_auto_ln_write(self):
        self.assertTrue(self.report['read_only'])
        self.assertTrue(self.report['human_approval_required'])
        self.assertTrue(all(x['review_required'] for x in self.report['results']))
    def test_model_extract_cannot_mark_verified(self):
        x=validate_extraction([dict(side='hit',field='dob',value='1999-01-01', evidence_id='model:1',origin='official_primary',checked=True)])[0]
        self.assertEqual(x.origin, 'model_extracted')
        self.assertFalse(x.checked)
    def test_unchecked_source_cannot_exclude(self):
        applicant=[Fact.from_dict(dict(side='applicant',field='dob',value='2000-01-01',evidence_id='a',origin='kyb_verified',checked=True))]
        hit=[Fact.from_dict(dict(side='hit',field='dob',value='1990-01-01',evidence_id='b',origin='model_extracted',checked=False))]
        self.assertFalse(evaluate(applicant,hit,'person').exclusion_rules)
    def test_masked_document_not_equal(self):
        app=[Fact.from_dict(dict(side='applicant',field='document_number',value='1101********1234',evidence_id='a',origin='kyb_verified',checked=True,context='CN_NATIONAL_ID'))]
        hit=[Fact.from_dict(dict(side='hit',field='document_number',value='1101********1234',evidence_id='b',origin='ln_structured',checked=True,context='CN_NATIONAL_ID'))]
        self.assertFalse(evaluate(app,hit,'person').linked_rules)
    def test_subject_isolation(self):
        raw=json.loads(json.dumps(case_data))
        raw['hits'][0]['subject_id']='c1'
        with self.assertRaises(ValueError): Case.from_dict(raw)
    def test_same_name_alerts_not_auto_merged(self):
        self.assertEqual(len(self.report['results']),len(case_data['hits']))

if __name__=='__main__': unittest.main()
