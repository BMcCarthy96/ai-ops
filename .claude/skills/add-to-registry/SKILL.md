---
name: add-to-registry
description: Add a new skill entry to skills/registry.yaml following the project schema
allowed-tools: Read, Edit
---

Collect from the user:
- Skill name (must follow `{category}.{action}.{target}` convention, e.g. `browser.validate.flow`)
- Category (one of: research, coding, qa, browser, ops, comms, knowledge — or a new one if justified)
- Description (one sentence)
- Required inputs (list)
- Expected outputs (list)
- Allowed tools (list of tool names the skill may use)
- Done criteria (list of conditions that define completion)
- Failure behavior (what to do when the skill cannot complete)

Then:
1. Read `skills/registry.yaml` to confirm the schema and find the right category section
2. Insert the new skill entry in alphabetical order within its category
3. Confirm the name follows `{category}.{action}.{target}` and does not duplicate an existing entry

## Schema reference

```yaml
- name: category.action.target
  category: <category>
  description: <one sentence>
  required_inputs:
    - <input 1>
    - <input 2>
  expected_outputs:
    - <output 1>
  allowed_tools:
    - <tool name>
  done_criteria:
    - <condition>
  failure_behavior: <what to do on failure>
```

## Important
- This file is a **definition registry only** — adding an entry here does not implement the skill
- If the skill is not yet implemented, add a comment: `# status: placeholder`
- Do not modify any other file
