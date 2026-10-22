import tempfile, os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine


def test_valid_evidence_accepted_and_persisted():
    with tempfile.TemporaryDirectory() as d:
        eng = ContextualAdaptationEngine(data_dir=d)
        ev = {"success": True, "verified": True, "impact_score": 0.9, "confidence": 0.9, "similar_observations": 3}
        res = eng.process_evidence_registration("v-ok", ev)
        assert res["processed"] is True
        assert res.get("verification_id") == "v-ok"
        regs = eng.knowledge_base.get("evidence_registrations", [])
        assert len(regs) == 1
        assert regs[0]["verification_id"] == "v-ok"


def test_minimum_evidence_threshold_respected():
    with tempfile.TemporaryDirectory() as d:
        eng = ContextualAdaptationEngine(data_dir=d)
        ev = {"success": True, "verified": True, "impact_score": 0.7, "similar_observations": 1}
        res = eng.process_evidence_registration("v-min", ev)
        assert res["processed"] is True
