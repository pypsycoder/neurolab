"""Apply bounded model-authored line replacements, not shell commands or Python edits."""
from pydantic import BaseModel, ConfigDict, Field
import json
import re


class LineReplacement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line: int = Field(ge=1, le=500)
    replacement: str = Field(max_length=200)


class CodeRepair(BaseModel):
    model_config = ConfigDict(extra='forbid')
    self_score: float = Field(ge=0, le=1)
    line_edits: list[LineReplacement] = Field(min_length=1, max_length=10)


def parse_repair_response(response) -> CodeRepair:
    if len(response.choices) != 1 or response.choices[0].finish_reason != 'stop':
        raise ValueError('repair response did not finish normally')
    content=response.choices[0].message.content
    if not isinstance(content,str) or len(content.encode())>8000:
        raise ValueError('repair output exceeds budget')
    fenced=re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*',content,re.DOTALL)
    if fenced:
        content=fenced.group(1)
    return CodeRepair.model_validate_json(content)


def repair_output_diagnostics(response):
    """Debug framing/schema only; no text, field values, messages or unknown keys."""
    if len(response.choices)!=1:
        return {'reason':'choice_count','choices':len(response.choices)}
    choice=response.choices[0]
    content=choice.message.content
    result={'reason':'repair_format','content_characters':len(content) if isinstance(content,str) else 0,
        'normal_stop':choice.finish_reason=='stop','fenced_json':False,'complete_json':False}
    if not isinstance(content,str) or len(content.encode())>8000:
        return result
    fenced=re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*',content,re.DOTALL)
    if fenced:
        result['fenced_json']=True; content=fenced.group(1)
    try:
        data=json.loads(content)
        result['complete_json']=True
        result['object']=isinstance(data,dict)
        if isinstance(data,dict):
            result['known_fields']=sorted(set(data)&{'self_score','line_edits','source_lines'})
            result['unknown_field_count']=len(set(data)-{'self_score','line_edits','source_lines'})
            result['line_edits_count']=len(data['line_edits']) if isinstance(data.get('line_edits'),list) else None
        try:
            CodeRepair.model_validate(data)
            result['schema_valid']=True
        except ValueError:
            result['schema_valid']=False
    except ValueError:
        pass
    return result


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
