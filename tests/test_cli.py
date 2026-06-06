"""The CLI is a thin adapter; this pins that its flags parse and wire through.
The planning behavior (incl. diversity_weight) is covered in test_planner."""

from mealplanner.cli import build_parser


def test_plan_diversity_flag_parses():
    # default is off
    assert build_parser().parse_args(["plan"]).diversity == 0.0
    # explicit value carries through (and coexists with the other plan flags)
    args = build_parser().parse_args(["plan", "--days", "5", "--household", "2", "--diversity", "2"])
    assert args.days == 5
    assert args.household == 2
    assert args.diversity == 2.0
