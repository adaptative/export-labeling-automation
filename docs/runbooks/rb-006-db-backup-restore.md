# RB-006: Database Backup & Restore

**Task:** TASK-046
**Last updated:** 2026-04-17

---

Labelforge uses Postgres 16 with row-level security (see `alembic/0002`).
Backups are taken via `pg_basebackup` + WAL archiving to S3, plus logical
snapshots every 4 h for fast table-level restores.

## Backup schedule

| Tier                   | Frequency    | Retention | Target                  |
|------------------------|--------------|-----------|-------------------------|
| Physical (basebackup)  | daily 02:00  | 30 days   | `s3://lf-db-physical`   |
| WAL continuous         | streaming    | 30 days   | `s3://lf-db-wal`        |
| Logical (pg_dump)      | every 4 h    | 14 days   | `s3://lf-db-logical`    |
| Cross-region replica   | streaming    | live      | `us-west-2-standby`     |

The `labelforge-db-backup` CronJob runs `pg_basebackup -D - -F tar | aws
s3 cp - ...` under its own IAM role.

## Verify backups

Run the smoke verification weekly:

```bash
kubectl -n labelforge create job --from=cronjob/labelforge-db-backup-verify \
  verify-$(date +%s)
kubectl -n labelforge logs -f job/verify-<ts>
```

The verifier downloads the latest tarball, starts a throwaway Postgres
in a tmpfs volume, and runs `SELECT count(*) FROM orders` etc. against it.

## Restore: point-in-time

```bash
# 1. Provision an empty Postgres 16 volume sized >= source.
# 2. Restore the most recent basebackup before the target time.
aws s3 cp s3://lf-db-physical/2026-04-17T02:00Z.tar.gz /var/lib/postgres/
tar xzf 2026-04-17T02:00Z.tar.gz -C /var/lib/postgres/

# 3. Configure recovery with the target timestamp.
cat >> /var/lib/postgres/postgresql.auto.conf <<EOF
restore_command = 'aws s3 cp s3://lf-db-wal/%f %p'
recovery_target_time = '2026-04-17 14:32:00 UTC'
recovery_target_action = 'promote'
EOF

# 4. Start Postgres, it will replay WAL then promote.
systemctl start postgresql
```

## Restore: logical / single-table

```bash
# Download the 4-h logical dump.
aws s3 cp s3://lf-db-logical/2026-04-17T12:00Z.dump /tmp/

# Restore a single table into a throwaway schema then copy the rows back.
pg_restore -h stg-db -U labelforge -d labelforge -j 4 \
  --schema=scratch_restore -t orders /tmp/2026-04-17T12:00Z.dump

psql -h stg-db -U labelforge -d labelforge <<SQL
BEGIN;
INSERT INTO orders SELECT * FROM scratch_restore.orders
  ON CONFLICT DO NOTHING;
DROP SCHEMA scratch_restore CASCADE;
COMMIT;
SQL
```

## Failover to cross-region replica

The `us-west-2-standby` follower replays WAL within ~3 s. To promote:

```bash
aws rds failover-db-cluster --db-cluster-identifier lf-db \
  --target-db-instance-identifier lf-db-standby
```

Point `DATABASE_URL` at the new primary, then run a rolling restart:

```bash
kubectl -n labelforge rollout restart deploy/api deploy/worker
```

## RTO / RPO targets

| Scenario                       | RPO      | RTO       |
|--------------------------------|----------|-----------|
| Primary instance failure       | 0 s      | 60 s      |
| Region outage (cross-region)   | < 10 s   | 5 min     |
| Logical corruption (single tbl)| 4 h      | 30 min    |
| Catastrophic loss (all tiers)  | 24 h     | 4 h       |

## Troubleshooting

| Symptom                                       | Action                                                  |
|-----------------------------------------------|---------------------------------------------------------|
| WAL archive lag > 30 s                        | Check S3 upload credentials; scale archiver pod         |
| Basebackup job fails with "replication slot"  | Clean up orphaned slot: `SELECT pg_drop_replication_slot(...)` |
| Restore replays but rows missing              | Wrong `recovery_target_time` — re-attempt with later TS |
| RLS policies missing after restore            | Re-apply `alembic upgrade head` on the restored cluster |
