## Vùng 1: AI + IaC Local Dev
(Môi trường sinh IaC)
### LLM / AI Engine
OpenAI / LLaMA / Ollama

↕ IaC validation feedback

### IaC Code Generation
AWS CDK (Python) — AWS
Ansible — private node

↓

### Local Validate
cdk synth · cdk diff
ansible-lin

> Pass/Commit -> go to Vùng 2

## Vùng 2: IaC Security Gate
(Cổng bảo mật IaC — scan · score · triển khai)
### IaC Code Repo
GitHub / GitLab · .py (CDK) · .yml
(Ansible)

↓

### IaC Security Scan
cdk synth → CloudFormation
Checkov · cfn-lint · ansible-lint
→ output JSON severity findings

↓ findings JSON → Risk Scoring Engine

### Risk Scoring Engine CDK
Input: Checkov · cfn-lint · ansible-lint ·
Infracost · AWS Config
Engine: Python Lambda · score = Σ(severity
× weight)
Store: SSM Parameter Store → score + findings
- Score ≤ 20
  ✓ Auto-pass
  → Plan/Apply
- Score 21–60
  ⚠ Review
  → Telegram
- Score > 60
  ✗ Auto-reject
  → re-gen Z1

↓ chỉ tiếp tục nếu score ≤ 20 hoặc approved

- ### IaC Plan / Dry-run
cdk diff · ansible --check --diff

↓

### IaC Apply → Provision
cdk deploy (EC2·VPC·SSM·EB…)
ansible-playbook (via Tailscale)

> scan reject -> quay lại Vùng 1 
> Risk reject > 60 -> quay lại Vùng 1
> cdk deploy -> AWS
> ansible -> private
> ↓
> Lambda re-trigger

## Vùng 3: Hybrid Infrastructure & Operational Monitoring
(CDK-provisioned · SSM · EventBridge · Monitoring)
### ☁ Hybrid Infrastructure — CDK deploy (AWS) · Ansible (private)
#### Public Cloud Free CDK
Oracle Cloud Always Free
2 OCPU · 1 GB · vĩnh viễn
AWS EC2 t2.micro
750h/tháng × 12 tháng
CDK: VPC · SG · EC2 · IAM
#### Hybrid Connector
Tailscale VPN
Free
≤100 thiết bị
WireGuard P2P
⟵ ⟶
Cloudflare
Tunnel Free
#### Private Node Miễn phí
Local / VirtualBox VM
Ubuntu 22.04 · ≥2GB
Raspberry Pi 4 (~$35)
Ansible manages:
pkg · svc · user · net

↓ SSM Agent (CDK user_data) · Hybrid Activation cho private node

### 🛠 AWS Systems Manager CDK

#### Managed Nodes
EC2: Free
Private: ~$4.17/node
Session Manager
Không cần SSH/bastion

#### State Manager CDK
Association Document
Config drift (OS-level)
ssm.CfnAssociation
Patch Manager

#### Parameter Store CDK
Standard: Free
Lưu Risk Score output
Config · secrets · vars
Inventory + Run Cmd

> ⚠ Non-compliant → CloudWatch Event → EventBridge · Risk score feedback → Zone 2

↓ SSM Compliance event → EventBridge → Lambda

### ⚡ EventBridge · Lambda · AWS Config CDK

#### EventBridge CDK
events.Rule
SSM Compliance Change
Config Rule violation
→ Risk Score re-calc
→ Lambda target

#### Lambda Remediation
lambda_.Function
Python 3.12
Gọi SSM Run Command
Re-trigger IaC CI
Rollback CDK stack

#### AWS Config CDK
config.ManagedRule
restricted-ssh
encrypted-volumes
→ violations score
→ Risk Engine input

> ✓ AWS Config violations → Risk Scoring Engine (Vùng 2) · Lambda re-trigger nếu cần

↓ Metrics: Prometheus HTTP API · CloudWatch API · Tailscale API · CloudTrail Logs

### 📊 Operational Monitoring — Mô hình B: Custom Dashboard

#### API Sources
Prometheus /api/v1/query
CloudWatch boto3
Tailscale /api/v2/device
SSM Parameter Store
GET risk_score → dashboard

#### AWS Data Layer
CloudWatch Metrics
AWS/EC2 · CWAgent
CloudTrail → CW Logs
Logs Insights (boto3)
Retention: 90 ngày (free)

#### Custom HTML Dashboard CDK
HTML + Chart.js · fetch API
CDK → S3 Static Website
Free hosting
Risk Score panel
color-coded by threshold

#### Alerting (no Alertmanager)
CloudWatch Alarms CDK
cloudwatch.Alarm
→ SNS → Telegram
RiskScore > 60 alarm
NodeDown · DiskFull

↓ Tổng hợp toàn cảnh hạ tầng hybrid

### SysSecOps Dashboard
Custom HTML Dashboard · CloudWatch Console · Uptime Kuma · AWS SSM · AWS Config · Risk Score Panel

> Lambda re-trigger -> Vùng 2

### 📊 Operational Monitoring — Mô hình A: Grafana Stack 

#### Data Collection
Prometheus (port 9090) · 15s
Node Exporter · Blackbox
CloudWatch Agent (EC2)
Tailscale logs → CW Logs
Risk Score metric (custom)
#### AWS Data Layer
CloudWatch Metrics
AWS/EC2 · CWAgent
CloudTrail → CW Logs
API audit · SSM changes
Logs Insights query
#### Grafana (port 3000) Free
Prometheus + CloudWatch
Dashboard ID: 1860 · 13978
11454 · 139
Risk Score panel
trend theo thời gian
#### Alerting Free
Alertmanager
→ Telegram · Discord
CloudWatch Alarms → SNS
Rules: NodeDown · HighCPU
RiskScore > 60 alert

↓ Tổng hợp toàn cảnh hạ tầng hybrid

### SysSecOps Dashboard
Grafana · Prometheus · Alertmanager · Uptime Kuma · AWS SSM · AWS Config · Risk Score Panel

# Risk Scoring Formula — dựa trên công cụ trong mô hình
### Input sources
Checkov → JSON findings
cfn-lint → JSON findings
ansible-lint → JSON findings
Infracost CLI → cost delta $
AWS Config → violations count
### Severity weights
CRITICAL × 30
HIGH × 10
MEDIUM × 5
LOW × 1
Cost >$10 + 15
Cost >$50 + 40
### Decision thresholds
Score 0–20
✓ Auto-pass → deploy
Score 21–60
⚠ Manual review
→ Telegram notify
Score > 60
✗ Auto-reject
→ re-trigger Zone 1
### Ví dụ tính score
Score = 8 → ✓ Auto-pass
2 MEDIUM(10) + 2 LOW(2) = 12.. wait
1 HIGH(10) - 2 LOW(2) = 12 pass
Score = 35 → ⚠ Review
1 HIGH(10) + 5 MEDIUM(25) = 35
Score = 75 → ✗ Reject
2 CRITICAL(60) + 1 MED(5) + $20 cost(15)