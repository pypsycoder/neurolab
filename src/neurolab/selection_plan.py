"""Use existing acquisition adapters with a stricter, task-linked catalog."""
from neurolab.corpus_gap_plan import plan_corpus_gaps
from neurolab.research_selection import VERSION, mission_for


def plan_selected_corpus(assessments, *, eligible_source_keys=frozenset(), **kwargs):
    admitted = tuple(a for a in assessments if a.source_key in eligible_source_keys)
    plan = plan_corpus_gaps(admitted, **kwargs)
    plan["policy_version"] = VERSION
    plan["raw_corpus_source_count"] = len({a.source_key for a in assessments})
    plan["selection_pending_or_excluded_count"] = len({a.source_key for a in assessments} - eligible_source_keys)
    template = plan["next_search"]
    if template:
        mission = mission_for(template["template_id"])
        plan["next_search"] = dict(template, topic=mission.topic, arxiv_terms=mission.arxiv_terms,
                                   goal=mission.goal, mission_id=mission.mission_id,
                                   lane=mission.lane, selection_policy=VERSION)
    plan["blocking_gaps"].append("task_selection_and_content_utility_required")
    return plan
