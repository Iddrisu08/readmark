# Runbook: Deploy & Rollback

## Normal deploy (automated)

Merging to `main` with changes under `backend/**` triggers `.github/workflows/deploy.yml`:

1. Build the Docker image.
2. Push to ECR as both `:<git-sha>` and `:latest`.
3. SSM `RunShellScript` → `readmark-deploy.sh` on the instance → pull `:latest`, restart container.

Watch it in the repo's **Actions** tab. Verify after:

```bash
curl -fsS http://<APP_IP>:8000/api/health
```

## Manual deploy

```bash
# Re-run the latest image on the box:
aws ssm start-session --target <INSTANCE_ID>
sudo /usr/local/bin/readmark-deploy.sh
```

Or trigger the workflow manually: Actions → **Deploy** → *Run workflow*.

## Rollback

Every build is tagged with its git SHA in ECR, so rollback = run a previous tag.

```bash
aws ssm start-session --target <INSTANCE_ID>

# List recent images (newest first)
aws ecr describe-images --repository-name readmark \
  --query 'sort_by(imageDetails,&imagePushedAt)[-5:].[imageTags[0],imagePushedAt]' \
  --output table

# Point :latest at a known-good SHA and redeploy
GOOD=<previous-sha>
REGISTRY=<acct>.dkr.ecr.us-east-1.amazonaws.com
aws ecr batch-get-image --repository-name readmark --image-ids imageTag=$GOOD \
  --query 'images[0].imageManifest' --output text | \
  aws ecr put-image --repository-name readmark --image-tag latest --image-manifest file:///dev/stdin
sudo /usr/local/bin/readmark-deploy.sh
```

Fastest path if you just need the previous image running: pull the SHA tag
directly and restart the container with it.

## Infra changes

Infra is Terraform (`infra/`). PRs run fmt/validate/plan (+ Infracost). Apply is
deliberate:

```bash
cd infra
terraform plan     # review
terraform apply    # execute
```

## Post-deploy checklist

- [ ] `/api/health` and `/api/ready` return 200
- [ ] A test register/login succeeds
- [ ] No error spike in CloudWatch Logs
- [ ] `/metrics` scrapeable
