from importlib.resources import files

from ..data import content_hash


def prompt(agent: str) -> tuple[str, str]:
    text = files("workstation").joinpath("prompts", f"{agent}.txt").read_text("utf-8")
    return text, content_hash(text)
