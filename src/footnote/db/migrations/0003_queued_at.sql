-- When an insight last joined the agents' queue: when it was found, and again when a correction
-- restates it. The agents measure how long a job has waited from here, so a restated insight starts
-- a fresh wait instead of inheriting the time since the moment it restates.
alter table insights add column queued_at timestamptz;
update insights set queued_at = created_at;
alter table insights alter column queued_at set default now(), alter column queued_at set not null;
