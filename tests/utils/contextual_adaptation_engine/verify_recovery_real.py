#!/usr/bin/env python3
import json, os, sys, tempfile, shutil
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine

def main():
    tmpdir = tempfile.mkdtemp(prefix='jarvis_recovery_')
    try:
        engine = ContextualAdaptationEngine(data_dir=tmpdir)
        report = engine.recovery_report()
        assert isinstance(report, dict)
        assert report.get('recoveries') == []
        assert report.get('count') == 0
        assert isinstance(report.get('files'), list)
        report['recoveries'].append({'x': 1})
        report2 = engine.recovery_report()
        assert report2.get('count') == 0

        rules_path = os.path.join(tmpdir, 'contextual_adaptation_rules.json')
        bad_rules = {'rules': [
            {'rule_id': 'r1', 'name': 'ok', 'condition_pattern': 'x', 'adaptation_actions': 'bad',
             'confidence_threshold': 0.7, 'context_triggers': ['production'], 'enabled': True, 'priority': 1, 'execution_count': 0}
        ]}
        with open(rules_path, 'w', encoding='utf-8') as fh:
            json.dump(bad_rules, fh)
        engine2 = ContextualAdaptationEngine(data_dir=tmpdir)
        assert engine2.load_adaptation_rules() is True
        assert 'r1' in engine2.adaptation_rules
        r = engine2.adaptation_rules['r1']
        assert isinstance(getattr(r, 'adaptation_actions'), list)
        rep = engine2.recovery_report()
        assert rep.get('count') >= 1
        assert 'adaptation_rules' in rep.get('files', [])
        print('0 comprobaciones fallidas')
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == '__main__':
    sys.exit(main())
