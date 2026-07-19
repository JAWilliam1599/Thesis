## Test risk model with others competitors

### Setup

This is where we compare our model with other baselines to see how effective our methods:

* CVSS: traditional risk scoring method (https://arxiv.org/abs/1908.04856, https://arxiv.org/abs/2603.12450) -> java
* Logistic Regression: interpreted, heavily uses in many papers (https://www.nature.com/articles/s41598-025-10291-9)
* Random Forest: (https://link.springer.com/article/10.1186/s42162-026-00640-x)
* XGBoost: (https://link.springer.com/article/10.1186/s42162-026-00640-x) (implemented)
* Our handcrafted method:

intuition:
probability hacker minimal solution has low risk (40%) - high profit

Metrics:
ROC-AUC: Score/100
Top-k: 


Features

For each finding:

Feature	Source
Severity	Semgrep/Bandit
Confidence	Semgrep/Bandit
CVSS	OWASP Dependency Check


Insecure_code: [SecurityEvalDataset](https://github.com/s2e-lab/SecurityEval)
Secure_code: randomly take from well-maintained projects (click, rich, typer, etc...)

Run logistic regression, we get this info:
              precision    recall  f1-score   support

           0       0.66      1.00      0.79        25
           1       1.00      0.46      0.63        24

    accuracy                           0.73        49
   macro avg       0.83      0.73      0.71        49
weighted avg       0.83      0.73      0.71        49

============================================================
Feature Importance
               Feature  Coefficient
4   bandit_conf_medium     0.680277
0          bandit_high     0.678995
10       total_semgrep     0.514541
1        bandit_medium     0.484828
7       semgrep_medium     0.396143
6         semgrep_high     0.355105
5      bandit_conf_low     0.178918
8          semgrep_low     0.097427
3     bandit_conf_high    -1.092557
9         total_bandit    -1.093509
2           bandit_low    -1.095737

There is some problem that the model can't detect the insecure, after examining the insecure dataset, we can see there are 58 CWEs that bandit+semgrep can't find problems => 50% of dataset. These problems varies mostly about misnumber counts. After eliminates and keep 15% outliers, we run again

Accuracy : 0.8709677419354839
Precision: 0.8666666666666667
Recall   : 0.8666666666666667
F1 Score : 0.8666666666666667
ROC AUC  : 0.8791666666666667

Confusion Matrix
[[14  2]
 [ 2 13]]

              precision    recall  f1-score   support

           0       0.88      0.88      0.88        16
           1       0.87      0.87      0.87        15

    accuracy                           0.87        31
   macro avg       0.87      0.87      0.87        31
weighted avg       0.87      0.87      0.87        31

============================================================
Feature Importance
               Feature  Coefficient
10       total_semgrep     1.136296
4   bandit_conf_medium     1.003949
6         semgrep_high     0.914679
7       semgrep_medium     0.720708
9         total_bandit     0.610932
1        bandit_medium     0.454592
0          bandit_high     0.435620
2           bandit_low     0.261740
3     bandit_conf_high     0.138912
5      bandit_conf_low     0.083852
8          semgrep_low     0.067123
============================================================