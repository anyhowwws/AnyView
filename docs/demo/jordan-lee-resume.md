# JORDAN LEE

Lead Cloud Platform Engineer · Singapore · jordan.lee@example.com · +65 8000 0000 · linkedin.com/in/jordan-lee-demo

*Fictional candidate for the AnyView demo. Any resemblance to a real person is coincidental.*

## SUMMARY

Cloud platform engineer with nine years across healthcare, logistics and payments. I move production systems to the cloud without customers noticing, build the paved roads that let product teams ship on their own, and lead small platform teams. Most at home where reliability, cost and developer speed pull in different directions.

## SKILLS

- Cloud: Google Cloud, Amazon Web Services (AWS), Cloud SQL for PostgreSQL, Amazon Kinesis, AWS Lambda
- Platform: Kubernetes, Terraform, GitLab CI/CD, Prometheus, Grafana, RabbitMQ
- Programming: Python, Java
- Practices: incident command, blameless postmortems, load testing, hiring and mentoring

## CERTIFICATIONS

- Google Cloud Certified Professional Cloud Architect — Google Cloud, 2023
- Certified Kubernetes Administrator (CKA) — The Linux Foundation, 2022
- HashiCorp Certified: Terraform Associate — HashiCorp, 2021
- AWS Certified Solutions Architect – Associate — Amazon Web Services, 2020

## EXPERIENCE

### Lead Cloud Platform Engineer — Kitebridge Payments
Mar 2022 – Present · Singapore

Responsibilities
- Lead a platform team of four engineers serving 14 product teams.
- Own the reliability of the card-payments platform: on-call rotation, incident command and postmortems.
- Set the Terraform and Kubernetes standards every product team builds on.

Projects
- Data centre exit to Google Cloud: our data centre lease was ending in 10 months and 42 payment services ran on ageing VMs. I designed the target architecture and led the migration to Kubernetes on Google Cloud, with every resource in Terraform and databases on Cloud SQL for PostgreSQL. Result: cut over with zero customer-facing downtime, infrastructure cost down 31%, deploy lead time from 2 days to 25 minutes.
- Paved Road developer platform: every team was hand-building its own pipelines and clusters. I built golden-path templates in Terraform and GitLab CI/CD that give a new service a pipeline, a namespace, dashboards in Grafana and alerts in Prometheus on day one. Result: a new service goes live in 2 days instead of 3 weeks; 12 of 14 teams adopted it within six months.

Key moments
- Black Friday checkout slowdown (2022): I approved an autoscaling change that set the payment gateway's scale-up threshold too high. On Black Friday traffic reached four times normal and checkout was degraded for 18 minutes. I took incident command, rolled the change back, and wrote and presented the blameless postmortem myself, naming my own approval as the root cause. I then added a load test at 5x peak as a required gate before any scaling change. Result: through the next two peak seasons we had no repeat, and p99 checkout latency stayed under 300 ms at 4x traffic.
- Pushing back on a six-week migration deadline (2022): our VP of Engineering wanted the whole data centre exit done in six weeks to hit a board date. I believed a big-bang cutover would put card payments at risk. I built a risk model service by service, showed which twelve services could not move safely in that window, and proposed a phased ten-week plan with the riskiest services last. Result: the VP agreed to the phased plan, the board date was met with the first 30 services, and the migration finished with zero customer-facing incidents.
- Building the platform team (2023): I inherited two engineers and an open headcount of two. I wrote the hiring loop, hired two engineers, and set up weekly one-to-ones and a rotation so each person led one project end to end. Result: two of the four were promoted within 18 months and nobody left the team.

What others said
- "Jordan turned a migration everyone feared into the calmest quarter we've had." — VP of Engineering, Kitebridge Payments, 2023 performance review

### Senior DevOps Engineer — Harbourline Logistics
Jul 2019 – Feb 2022 · Singapore

Responsibilities
- Ran the AWS environments for warehouse and fleet systems across five warehouses.
- Maintained the build pipelines and build infrastructure for 40 developers, and wrote Python tooling for environment provisioning.

Projects
- Build pipeline consolidation: three build tools, slow builds and a 20% failed-deploy rate. I moved every pipeline to GitLab CI/CD with shared templates and cached build stages. Result: average build time from 38 to 11 minutes, failed deploys down 60%.
- Warehouse telemetry pipeline: scanner and conveyor data reached dashboards 15 minutes late. I built a streaming pipeline on Amazon Kinesis and AWS Lambda feeding PostgreSQL and Grafana. Result: 2 million events a day, scan-to-dashboard latency from 15 minutes to 30 seconds.

Key moments
- Five warehouses, five different asks (2020): operations managers at each of the five warehouses wanted a different live dashboard and nobody could agree on requirements. Instead of waiting for a spec, I spent a day at each site watching the pickers, found the three numbers every site actually used, and shipped a thin prototype in two weeks for them to react to. Result: the dashboard was adopted at all five sites and mis-picks fell 12% in the first quarter.
- Getting security and developers onto one pipeline (2021): the security team reviewed every release by hand, so releases waited four days and developers had started to work around them. I sat down with the security lead, agreed which checks could be automated, built dependency and container scanning gates into GitLab CI/CD with them, and ran two workshops so developers understood what the gates caught. Result: security review went from four days to same-day, and no critical vulnerability reached production in the following 12 months.

What others said
- "Jordan listened to my floor managers before writing a line of code. That's why they use the dashboard." — Director of Warehouse Operations, Harbourline Logistics, 2020

### Software Engineer — Meridian Health Group
Aug 2016 – Jun 2019 · Singapore

Responsibilities
- Built and maintained Java services for clinic scheduling and patient records.
- Supported clinic staff as second-line on-call for the scheduling system.

Projects
- Appointment reminder service: 18% of outpatient appointments were no-shows. I built an SMS reminder service in Java with a retrying message queue on RabbitMQ. Result: no-show rate fell from 18% to 11% across 9 clinics.

Key moments
- Reminders before flu season (2018): the reminder service had to be live in eight weeks, before flu-season vaccinations, and our SMS provider throttled us to 50 messages a second. I designed the queue with batching and exponential back-off retries so a burst of 20,000 reminders would drain within the limit instead of failing. Result: we launched a week early, sent 120,000 reminders a month at 99.95% delivery, and never hit the provider's limit.
- Explaining a scheduling outage to clinic managers (2018): a database failover left the scheduling system read-only for two hours on a Monday morning and nine clinic managers were angry. I wrote a one-page plain-language account of what happened and what would change, and walked each manager through it on the phone that week. Result: the managers agreed to a monthly maintenance window, and complaints about the system fell to zero for the rest of the year.

## AWARDS

- Engineering Excellence Award — Kitebridge Payments, 2023, for the data centre exit

## EDUCATION

- Bachelor of Engineering (Computer Engineering) — National University of Singapore, 2012 – 2016

## LANGUAGES

- English — native
- Mandarin — professional working proficiency
