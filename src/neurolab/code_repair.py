"""Apply bounded model-authored line replacements, not shell commands or Python edits."""
from pydantic import BaseModel, ConfigDict, Field


class LineReplacement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line: int = Field(ge=1, le=500)
    replacement: str = Field(max_length=200)


class CodeRepair(BaseModel):
    model_config = ConfigDict(extra='forbid')
    self_score: float = Field(ge=0, le=1)
    line_edits: list[LineReplacement] = Field(min_length=1, max_length=10)


def apply_line_repair(source: str, proposal: CodeRepair) -> str:
    lines = source.splitlines()
    seen = set()
    for edit in proposal.line_edits:
        if edit.line > len(lines) or edit.line in seen or '\n' in edit.replacement or '\r' in edit.replacement:
            raise ValueError('line repair boundary invalid')
        seen.add(edit.line)
        lines[edit.line-1] = edit.replacement
    result = '\n'.join(lines)+'\n'
    if len(result.encode()) > 16000:
        raise ValueError('line repair source exceeds budget')
    return result
