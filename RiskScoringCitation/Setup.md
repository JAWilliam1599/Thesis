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
Objective findings -> phân loại vulnerabilities or not, chứ không detect

SUPPORTED_CWES = {
    20,
    22,
    77,
    78,
    79,
    89,
    94,
    95,
    190,
    200,
    295,
    327,
    330,
    352,
    434,
    502,
    611,
    798,
    918,
}
Second dataset with more samples and better visualize for analysis

Loaded insecure.csv
Loaded secure_dataset1.csv
Loaded secure_dataset2.csv
Loaded secure_dataset3.csv
========================================
Total samples : 482
Secure        : 195
Insecure      : 287
Saved to dataset.csv

============================================================


Logistic Regression
============================================================
Accuracy : 0.9259259259259259
Precision: 0.948051948051948
Recall   : 0.9012345679012346
F1 Score : 0.9240506329113924
ROC AUC  : 0.9233729614388051

Confusion Matrix
[[154   8]
 [ 16 146]]

              precision    recall  f1-score   support

           0       0.91      0.95      0.93       162
           1       0.95      0.90      0.92       162

    accuracy                           0.93       324
   macro avg       0.93      0.93      0.93       324
weighted avg       0.93      0.93      0.93       324

Feature Importance
               Feature  Importance
2           bandit_low    1.720216 --> giống expectations, bandit high cao, semgrep high --> tools quá yếu để có thể detect
3     bandit_conf_high    1.656566 --> unified ổn định cho các tools. --> khả năng phân biệt được vul khi có nhiều tools
9         total_bandit    1.555504
6         semgrep_high    0.790939
10       total_semgrep    0.546920
4   bandit_conf_medium    0.497096
0          bandit_high    0.381945
7       semgrep_medium    0.029059 --> traversal
8          semgrep_low    0.000000
1        bandit_medium   -0.359115
5      bandit_conf_low   -0.366808

============================================================

Random Forest
============================================================
Accuracy : 0.9166666666666666
Precision: 0.9299363057324841
Recall   : 0.9012345679012346
F1 Score : 0.9153605015673981
ROC AUC  : 0.9272976680384087

Confusion Matrix
[[151  11] --> 5%
 [ 16 146]]

              precision    recall  f1-score   support

           0       0.90      0.93      0.92       162
           1       0.93      0.90      0.92       162

    accuracy                           0.92       324
   macro avg       0.92      0.92      0.92       324
weighted avg       0.92      0.92      0.92       324

Feature Importance
               Feature  Importance
9         total_bandit    0.424089
3     bandit_conf_high    0.232883
2           bandit_low    0.200415
10       total_semgrep    0.047475
6         semgrep_high    0.02741
7       semgrep_medium    0.023943
4   bandit_conf_medium    0.021137
1        bandit_medium    0.009749
0          bandit_high    0.008271
5      bandit_conf_low    0.007296
8          semgrep_low    0.000000

limitations of tools

tools: KNN --> tìm những vùng bao hết tất cả các điểm --> không có học, tìm một vùng fit nhất --> overfit
SVMM --> tìm một đường thẳng nó ngăn hai khu vực

Logistic regression: phân tích P(vul) = w1*x1 + w2*x2
Khi có sự khác biệt với expectations, vẫn giải thích, dựa vô dataset, dựa do ý tưởng.
--> tìm trọng số mỗi một features. Phụ thuộc rất nhiều dataset. Phụ thuộc rất mạnh vào một features

Random Forest: phân tích rất nhiều decision trees --> combine features --> phù hợp cho tools distinct

XGBoost --> sửa lỗi sai. Phân biệt, false positives --> sửa lỗi, sửa trọng số, giảm false positives --> chạy lặp lại
