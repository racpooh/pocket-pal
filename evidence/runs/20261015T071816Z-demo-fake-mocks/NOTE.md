This run had a broken probe: the "B reads A's upload" and "delete one imported image" steps used a manual
transaction without an upload id, so the 404s here do not test ownership. Fixed in the next demo-fake-mocks run.
