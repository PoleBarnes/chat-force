# Mission

TestBot is a fixture persona used by the chat-force engine test suite.

It has no real customer, no real business, and no real deliverables.
Its sole purpose is to satisfy `HarnessLoader` validation so tests can
exercise the engine's harness-loading paths without requiring a real
customer harness.

If you are reading this because a test failed, the test is probably
asserting something about harness loading — not about this content.
