import unittest

from neurolab.gigachat_response_replay import (
    GigaChatResponseReplayError,
    request_synthetic_replay,
    synthetic_replay_cases,
)


class _Content:
    def __init__(self, text): self.text = text


class _Message:
    def __init__(self, text): self.content = [_Content(text)]


class _Response:
    def __init__(self, text): self.messages = [_Message(text)]


class _Chat:
    def __init__(self, outputs): self.outputs = iter(outputs); self.prompts = []
    def create(self, prompt):
        self.prompts.append(prompt)
        return _Response(next(self.outputs))


class _Client:
    def __init__(self, outputs): self.chat = _Chat(outputs)


class GigaChatResponseReplayTests(unittest.TestCase):
    def test_live_replay_cases_are_frozen_and_collect_only_in_memory(self):
        client = _Client(("synthetic public", "cannot patient", "metadata not verified", "cannot secret"))
        responses = request_synthetic_replay(client)
        self.assertEqual(tuple(responses), tuple(case.case_id for case in synthetic_replay_cases()))
        self.assertEqual(len(client.chat.prompts), 4)
        self.assertTrue(all("no tools" in prompt for prompt in client.chat.prompts))

    def test_oversized_response_fails_closed(self):
        client = _Client(("x" * 1601,))
        with self.assertRaises(GigaChatResponseReplayError):
            request_synthetic_replay(client)

    def test_v2_is_aligned_but_is_not_the_immutable_v1_prompt_set(self):
        v1 = synthetic_replay_cases("v1")
        v2 = synthetic_replay_cases("v2")
        self.assertEqual(tuple(case.case_id for case in v1), tuple(case.case_id for case in v2))
        self.assertNotEqual(v1, v2)
        client = _Client(("synthetic public", "cannot patient", "metadata not verified", "cannot secret"))
        request_synthetic_replay(client, variant="v2")
        self.assertEqual(len(client.chat.prompts), 4)
