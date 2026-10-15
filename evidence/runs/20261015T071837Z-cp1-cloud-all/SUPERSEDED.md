The `uses_mocks` field in this run's manifest.json is inaccurate: it was copied from the CP0 script and says "none",
but tests/integration use a FakeExtractionProvider and a ScriptedChatModel. Test outcomes are unaffected.
Superseded by the next `cp1-cloud-all` run, whose manifest lists the mocks correctly.
