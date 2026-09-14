# AWS IAM policies

The platform separates read and write permissions. Read access is used for all
of Phases 1–7; the write policy is introduced only in Phase 8 for the single
supported remediation action.

## Read — `read-policy.json`
Cost Explorer (`ce:GetCostAndUsage`), EC2/EBS/S3/RDS describe/list, CloudTrail
lookup, STS identity, and CloudWatch read for Bedrock usage metrics
(`cloudwatch:ListMetrics`, `cloudwatch:GetMetricData`). No write actions.

### Bedrock usage/cost intelligence
- **Cost**: `ce:GetCostAndUsage` filtered to the Bedrock service (already
  covered by the existing Cost Explorer permission).
- **Usage**: `cloudwatch:ListMetrics` + `cloudwatch:GetMetricData` against the
  `AWS/Bedrock` namespace (Invocations / InputTokenCount / OutputTokenCount).
  These are the only new read permissions this feature requires.

## Write (Phase 8) — `write-policy.json`
Exactly one action:

```
ec2:StopInstances
```

Keep this in a **separate** policy/role from the read permissions. The
application never stores AWS credentials; they are obtained at call time
through the credential abstraction, which can later assume a dedicated write
role instead of using a local profile.
