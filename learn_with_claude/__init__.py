"""learn_with_claude — simulate how a human learner uses Claude Code to learn a topic.

Two persistent `claude` CLI sessions are driven against each other:

  * a LEARNER persona (a role-played curious human) that emits its private
    *thinking* plus the *action* (message) it would actually type, and
  * a TUTOR (Claude) that responds to whatever the learner asks.

The learner drives the conversation the way a real person does — orienting,
asking for examples, getting confused, restating to check understanding — and
stops once it feels it has a solid working mental model.
"""

__version__ = "0.1.0"
