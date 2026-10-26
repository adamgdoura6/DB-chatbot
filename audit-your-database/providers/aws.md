# AWS RDS and Aurora

**Supported:** RDS for PostgreSQL and Aurora PostgreSQL. **Planned:** RDS/Aurora MySQL, DynamoDB (see
[README](README.md)).

## 1. Pick the endpoint
Use a **read replica** or the **Aurora reader endpoint** if you have one, so the audit's profiling queries never
load production. RDS console → your database → *Connectivity & security* → *Endpoint*.

## 2. Create a read-only role
Connect as the master user with your usual client and run [`readonly-role.sql`](readonly-role.sql) (change the
password). On a replica, run it on the primary; it replicates.

## 3. Network access
Most RDS instances sit in a private VPC. Pick one:

- **Publicly accessible instance:** allow your IP on port 5432 in the instance's security group.
- **SSH tunnel through a bastion host:**
  ```bash
  ssh -N -L 15432:<rds-endpoint>:5432 ec2-user@<bastion-host>
  ```
  Then connect to host `localhost`, port `15432`.
- **SSM port forwarding (no SSH, no open ports):**
  ```bash
  aws ssm start-session --target <ec2-instance-id> \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters host=<rds-endpoint>,portNumber=5432,localPortNumber=15432
  ```
  Then connect to host `localhost`, port `15432`.

Keep the tunnel open while the audit or the chatbot runs.

## 4. Connect
```bash
cd audit-your-database
python connect.py          # choose "AWS RDS / Aurora (PostgreSQL)"
```
SSL is required by default (`sslmode=require`). For full certificate checks, download the
[RDS CA bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) and append
`&sslmode=verify-full&sslrootcert=/path/to/global-bundle.pem` to the URL. Through a tunnel `verify-full`
fails on the hostname, so keep `require`.

IAM database authentication (short-lived tokens) is not supported yet; use a password login for `ai_reader`.

## Troubleshooting
| error | fix |
|---|---|
| `timeout expired` / `could not connect` | security group, VPC, or the tunnel is not running |
| `no pg_hba.conf entry ... no encryption` | keep `sslmode=require` in the URL |
| `permission denied for table` during the audit | re-run the per-schema block of `readonly-role.sql` for that schema |
