"""Actual, non-decorative Skill+Tool contract regression tests."""
from __future__ import annotations
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from ln_agent.skill_catalog import PRIMARY, ADDITIONAL, load_skill, select_skills
from ln_agent.tool_catalog import load_tool, available_for_call, tool_status
from ln_agent.skills import get_skill, ordered_queries
from ln_agent.policy_guard import PolicyGuard
from ln_agent.policy import Policy
from ln_agent import Case, FixtureResearchTool, Orchestrator

ROOT = Path(__file__).resolve().parents[1]

class ExplicitArchitectureTests(unittest.TestCase):
    def test_six_real_skills_exist(self):
        for slug in list(PRIMARY.values()) + sorted(ADDITIONAL):
            self.assertTrue((ROOT/'skills'/slug/'SKILL.md').exists())
            self.assertTrue(load_skill(slug)['id'])

    def test_skill_document_route_selected(self):
        names=[x['id'] for x in select_skills('person',['doc:notice'])]
        self.assertTrue(any('DOCUMENT_INTELLIGENCE' in n for n in names))
        self.assertTrue(any('PERSON_LN' in n for n in names))

    def test_suspicion_skill_selected_only_for_phase(self):
        a=[x['id'] for x in select_skills('person',[],phase='investigation')]
        b=[x['id'] for x in select_skills('person',[],phase='suspicion')]
        self.assertFalse(any('RESIDUAL_SUSPICION' in x for x in a))
        self.assertTrue(any('RESIDUAL_SUSPICION' in x for x in b))

    def test_primary_skill_contract_runtime_priority(self):
        base=get_skill('person')
        self.assertEqual(ordered_queries(base,['web:a','ln:b'])[0],'ln:b')
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'person_ln';path.mkdir()
            clone=dict(base);clone['preferred_sources']=['web','ln']
            (path/'contract.json').write_text(json.dumps(clone),encoding='utf-8')
            changed=load_skill('person_ln',root=Path(t))
            self.assertEqual(ordered_queries(changed,['web:a','ln:b'])[0],'web:a')

    def test_tool_catalog_offline_vs_not_connected(self):
        self.assertTrue(available_for_call('fixture_research',source_key='ln:abc')[0])
        self.assertTrue(available_for_call('document_intelligence',source_key='doc:x')[0])
        self.assertFalse(available_for_call('document_intelligence',source_key='web:x')[0])
        self.assertFalse(available_for_call('ln_readonly',source_key='ln:x')[0])
        self.assertEqual(tool_status()['qcc'],'not_connected')

    def test_policy_guard_reads_tool_and_skill_contracts(self):
        guard=PolicyGuard(Policy())
        skill=get_skill('person')
        self.assertTrue(guard.check_tool_call('fixture_research','official:demo',skill,0).allowed)
        changed=dict(skill);changed['allowed_tool_names']=[]
        self.assertFalse(guard.check_tool_call('fixture_research','official:demo',changed,0).allowed)
        self.assertFalse(guard.check_tool_call('ln_readonly','ln:abc',skill,0).allowed)

    def test_skill_hard_field_changes_actual_guard_decision(self):
        from ln_agent.policy_guard import PolicyViolation
        g = PolicyGuard(Policy())
        original = get_skill('person')
        g.validate_hard_rules(['DOB_EXACT_CONFLICT'], original)
        changed = dict(original)
        changed['blocked_exclusion_fields'] = list(original['blocked_exclusion_fields']) + ['dob']
        with self.assertRaises(PolicyViolation):
            g.validate_hard_rules(['DOB_EXACT_CONFLICT'], changed)

    def test_tool_manifest_has_non_decoration_entrypoint(self):
        for name in ('fixture_research','document_intelligence','fact_verification','source_corroboration'):
            self.assertTrue(load_tool(name)['runtime_entrypoint'])
        for name in ('ln_readonly','official_web','qcc','company_registry'):
            self.assertIsNone(load_tool(name)['runtime_entrypoint'])

    def test_run_hit_uses_contract_id(self):
        raw=json.loads((ROOT/'examples/case_false_positive.json').read_text(encoding='utf-8'))
        d=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(raw))['results'][0]
        self.assertIn('SKILL_PERSON_LN',d['version_snapshot']['skills'])
        self.assertIn('skill_bundle',d['history'][0])

if __name__ == '__main__': unittest.main()
