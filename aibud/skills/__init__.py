from .game_maker import build_arcade_skill
from .report_writer import build_report_skill

SKILLS = {
    "build_arcade": build_arcade_skill,
    "write_report": build_report_skill,
}
