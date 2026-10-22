import tempfile, os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine


def test_insufficient_evidence_rejected():
    with tempfile.TemporaryDirectory() as d:
        eng = ContextualAdaptationEngine(data_dir=d)
        res = eng.process_evidence_registration("v1", {"success": False, "verified": False})
        assert res["processed"] is False
        assert res["reason"] == "insufficient_evidence"
        assert "evidence_registrations" not in eng.knowledge_base or not eng.knowledge_base.get("evidence_registrations")


def test_valid_evidence_persisted():
    with tempfile.TemporaryDirectory() as d:
        eng = ContextualAdaptationEngine(data_dir=d)
        ev = {"success": True, "verified": True, "impact_score": 1.0, "similar_observations": 5}
        res = eng.process_evidence_registration("v2", ev)
        assert res["processed"] is True
        assert len(eng.knowledge_base.get("evidence_registrations", [])) == 1
