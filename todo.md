## Risk Scoring and Gate

I notice that infracost require user to run infracost setup first to get the api key. but can we set api key for infracost in .env and require user to input in UI like other env values

at this moment, we have 2 risk scoring points: one for cdk and one for ansible. 

i want to integrate the model in riskScoringCitation/ folder to current risk scoring and security gate. but i did not work on the formula yet. any suggestion?

## Monitor

- need more dashboards in UI app for resources
  - we can use automatic dashboards by aws for monitoring resources like ec2, rds, etc. we already have separate group for each stack
  - for on-premise resources too
- should have 2 tabs for monitoring: one for resources and one for the app statistics like gate and risk scoring points, user activity, etc.

## UI
Current UI is for cdk only. we need to update the UI to support both workflows.


### workflow for UI

the user may have multiple projects and each project may have different workflow. we should allow user to choose the workflow for each project.
- the app should save data for each project. especially for monitoring data, we should save the data for each project separately. 

we should let the user to choose the workflow for each project. we can have 2 workflows: 
- hybrid workflow 
  - this workflow do not have code generation but allow user input the folder for of cdk and ansible
- cdk only
  - which have code generation
  - the pipeline allow regeneration steps

## Demo 
> Do not make a plan for this section yet

this can be do after we finish all parts above


we will have 2 demos for 2 workflows. one for hybrid workflow and one for cdk only workflow

- cdk workflow
  - we will go through the pipeline include 
    - code generation
    - risk scoring and security gate
    - synth and deploy
    - monitoring for resources and app statistics

- hybrid workflow
  - currently we have 1 demo for hybrid in examples/hybrid-webapp-demo/demo-hybrid/
  - but we can have a better demo which we add a component for ansible 