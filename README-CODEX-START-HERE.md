# Take A Number — Codex Start Here

## Read first

Before changing code, read:

1. `AGENTS.md`
2. `docs/requirements.md`
3. `docs/architecture.md`
4. `docs/data-model.md`
5. `docs/implementation-plan.md`

## Current development assumptions

- GitHub repository already exists and is cloned locally.
- Python virtual environment already exists.
- Required Python packages have been installed.
- `requirements.txt` has already been frozen.
- PostgreSQL is the database from the beginning.
- SQLite is not supported.
- The first coding target is Milestone 0 only.

## How to use the prompt files

Run prompts in order.

Do not combine all milestones into one Codex task.

Recommended sequence:

1. `prompts/00-audit-repo.md`
2. `prompts/01-foundation.md`
3. Review changes and commit.
4. `prompts/02-auth.md`
5. Continue milestone-by-milestone.

After each milestone:

- review diff
- run tests yourself
- commit
- create a new branch/task for the next milestone where appropriate

## Important product constraints

- students do not log in
- do not collect student location
- pseudonymous browser identity is allowed
- optional entered student name is allowed
- multi-instructor ownership boundaries are mandatory
- PostgreSQL only
- real-time queue state uses Flask-SocketIO
- initial production model is single-worker/no Redis
