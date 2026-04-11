from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from itsm_openenv_benchmark.environment import ITSMEnvironment
from itsm_openenv_benchmark.models import ITSMAction


def test_reset_and_single_step() -> None:
    env = ITSMEnvironment()
    obs = env.reset(task_id="ITSM-001")

    assert obs.task_id == "ITSM-001"
    assert obs.task_type in {"incident", "incident_sla", "problem", "incident_knowledge"}

    result = env.step(ITSMAction(action_type="query", target_id="ITSM-001", payload={}))

    assert result.observation.step_index == 1
    assert isinstance(result.done, bool)
