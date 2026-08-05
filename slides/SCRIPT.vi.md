# Kịch bản thuyết trình — Bảo vệ khóa luận 20 phút

**Đề tài:** Nghiên cứu và Xây dựng Quy trình SysSecOps cho Môi trường Hybrid Cloud
**Người trình bày:** Nguyễn Chính Thông (22125102) · Huỳnh Tuấn Minh (22125055)
**Tổng thời lượng nói:** ~19:45, sau đó là phần hỏi đáp

## Cách sử dụng kịch bản này

- Mỗi mục tương ứng với một slide trong [slides/presentation.md](slides/presentation.md), theo đúng thứ tự.
- **Nói:** là phần lời thoại, viết để đọc ở tốc độ khoảng 140 từ/phút.
- **Không đọc bảng.** Ở những slide có bảng, kịch bản chỉ nói những gì bảng không tự nói được.
- Dòng *(Chỉ dẫn)* là hướng dẫn sân khấu — chỉ tay, dừng nhịp, chuyển slide — không phải lời nói.
- Phân vai đề xuất: **Người A** trình bày slide 1–17 (bài toán, quy trình, engine chấm rủi ro); **Người B** trình bày slide 18–28 (hệ thống, đánh giá, kết luận). Câu chuyển vai đã được viết sẵn ở slide 18.
- Thuật ngữ kỹ thuật (hybrid cloud, gate, pass/review/reject, tên công cụ) giữ nguyên tiếng Anh để khớp với slide.

---

## Phần 0 — Mở đầu (1:00)

### Slide 1 — Trang bìa (0:30)

**Nói:**
> Kính chào Chủ tịch hội đồng và quý thầy cô. Chúng em xin cảm ơn hội đồng đã dành thời gian cho buổi bảo vệ hôm nay.
>
> Khóa luận của chúng em có tên *Nghiên cứu và Xây dựng Quy trình SysSecOps cho Môi trường Hybrid Cloud*. Em là Nguyễn Chính Thông, và đây là bạn Huỳnh Tuấn Minh. Đề tài được hướng dẫn bởi TS. Trần Trung Dũng và ThS. Chung Thùy Linh, thuộc Chương trình Tiên tiến ngành Khoa học Máy tính, Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM.
>
> Chúng em sẽ trình bày trong khoảng hai mươi phút, sau đó xin lắng nghe câu hỏi của hội đồng.

*(Chỉ dẫn: chuyển slide ngay — không dừng lâu ở trang bìa.)*

---

### Slide 2 — Lộ trình trình bày (0:30)

**Nói:**
> Đây là những nội dung chúng em sẽ đi qua.
>
> Thứ nhất, bài toán: vì sao vận hành hybrid cloud làm suy yếu bảo mật. Thứ hai, quy trình chúng em đề xuất — một quy trình SysSecOps có chốt quyết định đặt *trước* khi triển khai. Thứ ba, engine chấm rủi ro biến nhiều công cụ rời rạc thành một quyết định giải thích được. Thứ tư, những gì chúng em đã thực sự xây dựng. Thứ năm, kết quả, được tổ chức thành ba câu hỏi nghiên cứu với ba khối bằng chứng riêng biệt. Cuối cùng là hạn chế và hướng phát triển.
>
> Một điểm xin lưu ý trước: phần đánh giá ánh xạ một-đối-một với các câu hỏi nghiên cứu, nên mọi khẳng định đều có một vị trí cụ thể chứa bằng chứng của nó.

---

## Phần 1 — Bài toán và định vị (3:30)

### Slide 3 — Động lực nghiên cứu (0:45)

**Nói:**
> Các tổ chức chọn hybrid cloud vì họ muốn hai thứ cùng lúc: tính co giãn của public cloud, và quyền kiểm soát trên hạ tầng họ sở hữu. Sự kết hợp đó hiện là mô hình vận hành mặc định, không còn là trường hợp cá biệt.
>
> Nhưng nó có cái giá của nó. Một hạ tầng hybrid có hai cơ chế cấp phát, hai mô hình bảo mật, và hai miền định danh. Dạng lỗi phổ biến nhất không còn là một kỹ thuật khai thác mới lạ, mà là cấu hình lệch chuẩn và cấu hình sai — những sai lệch nhỏ tích tụ dần trên hai môi trường vốn không được thiết kế để quản trị chung.
>
> Và trên thực tế, việc cấp phát, quản trị hệ thống, phân phối phần mềm và đánh giá bảo mật lại do các nhóm khác nhau với các bộ công cụ khác nhau đảm nhiệm. Vậy nên tính linh hoạt là có thật — và chi phí phối hợp cũng có thật.

---

### Slide 4 — Bốn thách thức vận hành (0:45)

**Nói:**
> Chúng em nhóm chi phí đó thành bốn thách thức.
>
> *(Chỉ dẫn: chỉ vào bảng, không đọc bảng.)*
>
> **C1**, quản lý hạ tầng không đồng nhất — cùng một chính sách phải có hiệu lực trên các tài nguyên on-premises, private và public vốn không dùng chung ngôn ngữ mô tả.
>
> **C2**, tích hợp bảo mật liên tục vào vòng đời. Bảo mật thường được áp dụng muộn, khiến việc khắc phục vừa tốn kém vừa chậm trễ.
>
> **C3**, đánh giá phát hiện và xếp thứ tự ưu tiên rủi ro. Nhiều công cụ, nhiều định dạng đầu ra, và không có cách nhất quán để nói phát hiện nào quan trọng hơn.
>
> **C4**, xây dựng một quy trình tích hợp. SysAdmin, phát triển và bảo mật hoạt động rời rạc, nên các quyết định được đưa ra mà không có khả năng truy vết.

---

### Slide 5 — Khoảng trống nghiên cứu (0:45)

**Nói:**
> Bốn thách thức này tương ứng với bốn khoảng trống trong các nghiên cứu đã có.
>
> **G1** — có rất ít khung vận hành cho bảo mật hybrid cloud. Kiến trúc tham chiếu của NIST định nghĩa các thành phần *là gì*; nó không định nghĩa *làm thế nào* để vận hành chúng cùng nhau.
>
> **G2** — bảo mật liên tục phần lớn dừng lại ở CI/CD. Nó hiếm khi được mở rộng sang vận hành hạ tầng trong môi trường không đồng nhất.
>
> **G3** — có rất ít nghiên cứu về điều phối các công cụ bảo mật khác loại. Các nghiên cứu phân loại công cụ; ít công trình hợp nhất đầu ra của chúng thành một quyết định duy nhất.
>
> **G4** — kiểm chứng thực nghiệm còn hạn chế. Các kiến trúc khái niệm chiếm ưu thế; quy trình chạy được và được đánh giá thì rất hiếm.
>
> Mỗi khoảng trống đều được neo vào một công trình đã công bố, nên đây không phải là nhận định chủ quan của chúng em.

---

### Slide 6 — Khoảng trống → Mục tiêu → Câu hỏi → Đóng góp (0:45)

**Nói:**
> Bảng này là trục logic của toàn bộ khóa luận, nên em xin đi trọn vẹn một hàng.
>
> Khoảng trống một và bốn — chưa có khung vận hành, và kiểm chứng thực nghiệm còn yếu. Mục tiêu tương ứng là *thiết kế* một quy trình SysSecOps tích hợp quản lý hạ tầng, đánh giá, cưỡng chế và triển khai. Câu hỏi nghiên cứu kiểm chứng nó là **RQ1**: hệ thống có đưa ra đúng quyết định cần đưa ra hay không, và quyết định đó có thực sự ràng buộc những gì xảy ra tiếp theo hay không. Đóng góp là chính quy trình đó.
>
> Mọi hàng còn lại đều theo đúng khuôn mẫu này. Khoảng trống hai dẫn tới **RQ2**, cưỡng chế xuyên biên giới. Khoảng trống ba dẫn tới **RQ3**, đánh giá rủi ro hợp nhất. Không có phần nào trong đánh giá mà không có một khoảng trống đứng sau nó.

---

### Slide 7 — Đóng góp (0:30)

**Nói:**
> Ba đóng góp, mỗi đóng góp một câu.
>
> **C1** — một quy trình vận hành SysSecOps cho hybrid cloud, đưa quản trị hệ thống, bảo mật liên tục và phân phối phần mềm về cùng một luồng công việc với *một đường quyết định chung* cho cả mục tiêu public và private.
>
> **C2** — một cơ chế đánh giá bảo mật hợp nhất, chuẩn hóa và khử trùng lặp phát hiện từ nhiều công cụ khác loại, rồi kết hợp chúng với chi phí, tuân thủ thời gian thực và một tín hiệu rủi ro mã nguồn học được, thành một điểm số giải thích được.
>
> **C3** — một hệ thống nguyên mẫu chạy được và một khung đánh giá tái lập được, với tiêu chí chấp nhận riêng cho từng câu hỏi nghiên cứu.

---

## Phần 2 — Quy trình đề xuất và kiến trúc (3:55)

### Slide 8 — Ý tưởng cốt lõi: chốt trước khi triển khai (0:45)

**Nói:**
> Nếu hội đồng chỉ ghi nhớ một quyết định thiết kế từ bài trình bày này, xin cho phép đó là quyết định sau đây.
>
> Quyết định bảo mật được đưa ra trên **artefact đã được sinh ra** — tức template CloudFormation, hoặc Ansible play đã được phân giải. Không phải trên prompt, và cũng không phải trên mã nguồn mức cao. Đây là lựa chọn có chủ đích: artefact đã sinh là biểu diễn cuối cùng trước khi bất kỳ tài nguyên nào tồn tại, và là điểm đầu tiên mà mọi tài nguyên cùng mọi thuộc tính đều đã được biết đầy đủ. Quyết định sớm hơn nghĩa là quyết định trên thông tin thiếu; quyết định muộn hơn nghĩa là quyết định sau khi rủi ro đã xảy ra.
>
> Điểm thứ hai: một engine duy nhất cho toàn bộ hybrid. Cùng trọng số, cùng luật khử trùng lặp, cùng ngưỡng ở cả hai phía của ranh giới tin cậy.
>
> Hai lựa chọn đó, cộng với suy giảm có kiểm soát, khả năng kiểm toán, khắc phục theo vòng phản hồi và khả năng quan sát, là các mục tiêu thiết kế mà kiến trúc phải thỏa mãn.

---

### Slide 9 — Kiến trúc tham chiếu ba vùng (0:50)

**Nói:**
> Kiến trúc gồm ba vùng.
>
> **Vùng 1** là sinh mã có hỗ trợ AI và kiểm tra cục bộ — mã được sinh ra từ prompt và được kiểm tra tại chỗ bằng `cdk synth`, `cdk diff`, hoặc kiểm tra cú pháp.
>
> **Vùng 2** là security gate. Phân tích đa công cụ, khử trùng lặp chéo nguồn, chấm điểm rủi ro, và quyết định triển khai. Vùng này chính là đóng góp của khóa luận.
>
> **Vùng 3** là hạ tầng hybrid và giám sát vận hành — cấp phát trên AWS và on-premises, thu thập telemetry, cùng vòng phát hiện lệch chuẩn và khắc phục.
>
> *(Chỉ dẫn: chỉ vào cạnh phản hồi nét đứt.)*
>
> Xin hội đồng lưu ý cạnh này. Khi mã sinh ra bị từ chối, các phát hiện được đưa ngược vào prompt kế tiếp và mã được sinh lại. Khắc phục là một phần của vòng lặp, không phải một việc thủ công tách rời.
>
> Ba vùng ghép lỏng với nhau: Vùng 1 không biết gì về luật chấm điểm, và Vùng 3 không biết gì về cách quyết định được đưa ra.

---

### Slide 10 — Luồng artefact đầu-cuối (0:50)

**Nói:**
> Đây vẫn là hệ thống đó, nhìn dưới góc độ dòng chảy của artefact. Một prompt hoặc một dự án có sẵn trở thành mã được sinh; mã được sinh trở thành template đã tổng hợp; template trở thành tập phát hiện đã chuẩn hóa; các phát hiện trở thành điểm số và quyết định; quyết định trở thành gate report; và chỉ đến lúc đó mới có triển khai và telemetry. Nếu quyết định là *reject*, chúng ta quay lại và sinh lại mã.
>
> Mỗi chặng biến đầu vào của nó thành một biểu diễn cụ thể hơn hẳn.
>
> Thứ giữ toàn bộ hệ thống lại với nhau là ba hợp đồng dữ liệu ổn định. **Gate report** mang điểm số, quyết định, phân rã theo từng thành phần, danh sách phát hiện đã khử trùng lặp, và trạng thái của từng scanner. **Execution result** nghĩa là mọi lệnh ngoại vi đều trả về cùng một cấu trúc — mã trả về và đầu ra của nó. Còn **gate-decision event** được phát lên SSM Parameter Store và EventBridge.
>
> Vì các hợp đồng này ổn định, bộ sinh mã, tập scanner và tầng giám sát có thể tiến hóa độc lập với nhau.

---

### Slide 11 — Cấu trúc triển khai hybrid (0:45)

**Nói:**
> Cụ thể, phía public là AWS: CDK tổng hợp CloudFormation cho VPC, EC2, S3 và RDS, cùng với SSM, EventBridge, CloudWatch, CloudTrail, một Lambda ops-loop và SNS cho tầng vận hành.
>
> Phía private là các node Linux on-premises được cấu hình bằng Ansible và đăng ký qua SSM hybrid activation, nơi chúng xuất hiện dưới dạng managed instance có tiền tố `mi-`.
>
> **Không có truy cập quản trị từ Internet vào bên trong.** Toàn bộ control plane đi qua kênh đã mã hóa.
>
> Và kênh đó là một thành phần có thể thay thế. Chúng em dùng mesh overlay VPN, nhưng site-to-site IPsec VPN, Direct Connect, Transit Gateway, hay SSM qua public endpoint đều là lựa chọn hợp lệ. Điểm quan trọng là lựa chọn đó không làm thay đổi bất cứ điều gì trong gate, trong cách chấm điểm, hay trong hành vi quản trị — kết nối là vấn đề trực giao với đóng góp của khóa luận.

---

### Slide 12 — Quản trị và cưỡng chế (0:45)

**Nói:**
> Quyết định có ba kết cục. **Pass** thì triển khai tự động. **Review** thì chặn triển khai cho tới khi tồn tại một bản ghi phê duyệt tường minh. **Reject** thì không triển khai — thay đổi được sinh lại hoặc trả về cho tác giả.
>
> Mọi quyết định đều được lưu thành bản ghi bất biến kèm danh tính người thực hiện, nên vết kiểm toán chỉ được ghi thêm, không bị sửa.
>
> Ngoài ra còn có hợp đồng suy giảm có kiểm soát. Nếu thiếu binary của một scanner, hoặc thiếu credential, nguồn đó suy giảm về trạng thái `skipped` được định nghĩa rõ ràng. Gate vẫn đưa ra quyết định, và report vẫn ghi lại *những nguồn nào* đã thực sự chạy — nên một quyết định có ít bằng chứng thì nhìn thấy được, chứ không âm thầm. Chúng em sẽ quay lại điểm này, vì đây chính là nơi một trong hai kết quả tiêu cực của chúng em nằm.
>
> Cuối cùng, credential không bao giờ được truyền qua tham số dòng lệnh; chúng được phân giải qua provider chain và đưa vào qua biến môi trường.

---

## Phần 3 — Đánh giá bảo mật hợp nhất và chấm điểm rủi ro (3:40)

### Slide 13 — Vì sao chỉ dùng mức nghiêm trọng là không đủ (0:40)

**Nói:**
> Vì sao lại cần xây một điểm số, thay vì chỉ dùng nhãn mức nghiêm trọng?
>
> Ba lý do. Thứ nhất, mức nghiêm trọng bỏ qua phạm vi ảnh hưởng và chi phí. Cùng một luật security group mở, đặt trên load balancer hướng Internet và đặt trên một subnet biệt lập, mang cùng một nhãn nghiêm trọng nhưng mức phơi nhiễm thì hoàn toàn khác nhau.
>
> Thứ hai, mọi công cụ đều có điểm mù. Một scanner chính sách, một trình lint template, một công cụ ước tính chi phí, một dịch vụ tuân thủ thời gian thực và một mô hình mã nguồn — mỗi thứ nhìn thấy một lát cắt khác nhau của cùng một thay đổi. Dựa vào bất kỳ công cụ đơn lẻ nào cũng tạo ra âm tính giả có hệ thống.
>
> Thứ ba, việc sinh mã bằng AI làm dịch chuyển hồ sơ rủi ro. Dạng lỗi phổ biến nhất của mã hạ tầng do AI sinh ra không phải là một lỗ hổng mới lạ — mà là một *cấu hình sai nhưng trông rất hợp lý*. Do đó, một xác suất học được rằng mã là không an toàn cũng hữu ích không kém bất kỳ luật viết tay nào.

---

### Slide 14 — Đánh giá đa công cụ và chuẩn hóa (0:45)

**Nói:**
> Vì vậy gate chạy bảy nguồn trên bốn chiều rủi ro.
>
> *(Chỉ dẫn: lướt tay theo cột, không đọc từng hàng.)*
>
> Với chiều **cấu hình sai**: `cfn-lint` kiểm tra tính hợp lệ của CloudFormation, Checkov cho policy-as-code, `ansible-lint` cho phía private, và một scanner regex tìm credential nhúng cứng. Với chiều **chi phí**: Infracost, cho ra chênh lệch chi phí hàng tháng ước tính. Với chiều **tuân thủ**: AWS Config, cho ra số luật không tuân thủ trên hệ thống thật. Và với chiều **rủi ro mã nguồn**: đặc trưng từ Bandit và Semgrep đưa vào một mô hình hồi quy logistic.
>
> Đầu ra của chúng được chuẩn hóa về một định dạng phát hiện chung, rồi khử trùng lặp theo khóa `(resource_id, template, category)`. Các phát hiện va nhau sẽ được gộp, giữ mức nghiêm trọng cao nhất và hợp nhất nhãn nguồn.
>
> Khử trùng lặp không phải chuyện hình thức. Nếu không có nó, một vấn đề được ba công cụ báo sẽ đóng góp ba lần, và chỉ riêng điều đó đã đủ đẩy một thay đổi vốn chấp nhận được vượt qua ngưỡng.

---

### Slide 15 — Điểm rủi ro cộng tính (0:50)

**Nói:**
> Điểm số là tổng của bốn thành phần.
>
> Thành phần **mức nghiêm trọng** cộng trọng số trên các phát hiện đã khử trùng lặp — critical là hai mươi điểm, high là mười, medium năm, low một. Thành phần **chi phí** là một hàm chia dải trên chênh lệch ước tính. Thành phần **tuân thủ** là năm điểm cho mỗi luật không tuân thủ trên hệ thống thật. Và thành phần **học máy** là xác suất của mô hình, quy đổi về thang hai mươi điểm.
>
> Chi phí được chia dải thay vì để liên tục — đây là chủ đích, để điểm số ổn định trước nhiễu của ước tính, thay vì nhảy theo từng biến động giá.
>
> Về ngưỡng: từ hai mươi trở xuống là pass, hai mươi mốt tới tám mươi là review, trên tám mươi là reject.
>
> Em xin nói rõ một điều. Dạng cộng tính này là một *đơn giản hóa có chủ đích* của một mô hình rủi ro đa yếu tố tổng quát. Chúng em chọn nó vì tính minh bạch và khả năng tái lập — vì nó cộng tính, mỗi điểm đều quy được về một thành phần, và đó chính là thứ khiến báo cáo giải thích được.

---

### Slide 16 — Thành phần rủi ro mã nguồn bằng học máy (0:45)

**Nói:**
> Thành phần học được, gói trong một phút.
>
> Mẫu dương lấy từ **SecurityEval**, tập mã Python không an toàn có gán nhãn CWE. Mẫu âm lấy từ các dự án được bảo trì tốt — `click`, `rich` và `typer`. Đặc trưng là vector đếm mười một chiều: số phát hiện Bandit theo mức nghiêm trọng và theo độ tin cậy, số phát hiện Semgrep theo mức nghiêm trọng, và hai giá trị tổng. Mô hình là hồi quy logistic trên phân chia phân tầng tám mươi–hai mươi, với đặc trưng đã chuẩn hóa và trọng số lớp cân bằng.
>
> Huấn luyện và suy luận dùng cùng bộ phân tích, cùng cách nhóm, và cùng một scaler đã lưu — nên không có lệch giữa huấn luyện và vận hành.
>
> Khi suy luận, xác suất là giá trị **lớn nhất** trên các tệp, không phải trung bình. Tệp tệ nhất thắng, nên một tệp rủi ro không thể bị pha loãng bởi nhiều tệp lành tính.
>
> Và em xin chủ động nêu phạm vi: mô hình này ước lượng mức không an toàn **mà công cụ phân tích nhìn thấy được**. Nó không phát hiện các lỗi ngữ nghĩa mà Bandit và Semgrep không thấy. Khoảng một nửa số mẫu SecurityEval gốc chứa đúng loại lỗi logic đó; giữ chúng lại khiến recall bị chặn quanh 0.46, và đó là lý do chúng bị loại ra, cũng là lý do khẳng định được giới hạn phạm vi như vậy.

---

### Slide 17 — Ví dụ minh họa (0:40)

**Nói:**
> Một trường hợp cụ thể. Một thay đổi tạo ra một phát hiện mức high và hai phát hiện mức medium sau khử trùng lặp, rơi vào dải chi phí trung bình, có một luật không tuân thủ trên hệ thống thật, và mô hình trả về xác suất bằng không.
>
> Mức nghiêm trọng cho mười cộng năm cộng năm, tức hai mươi. Chi phí cho mười. Tuân thủ cho năm. Mô hình cho không. Tổng: ba mươi lăm. Con số này trên hai mươi và dưới tám mươi, nên quyết định là **review**, và nó được chuyển tới người phê duyệt, và quyết định của người đó đi vào vết kiểm toán.
>
> Nhưng xin hội đồng chú ý người phê duyệt thực sự nhận được gì. Bảng phân rã — nghiêm trọng hai mươi, chi phí mười, tuân thủ năm, mô hình không — cho họ biết cổng quản trị đang mở và mức tăng chi phí mới là hai yếu tố chi phối. Điều đó định hướng việc khắc phục một cách chính xác, thay vì trao cho họ một con số mờ đục. Đây chính là câu trả lời của chúng em cho câu hỏi "vì sao không dùng luôn một mô hình hộp đen".

---

## Phần 4 — Hiện thực và đánh giá (6:10)

### Slide 18 — Hệ thống nguyên mẫu (0:45)

**Nói (chuyển vai):**
> Cảm ơn bạn. Em xin tiếp tục phần hiện thực và kết quả.
>
> Nguyên mẫu là một hệ thống Python gồm bảy module. `generation` phụ trách sinh mã qua lớp trừu tượng nhà cung cấp, dùng Bedrock hoặc OpenRouter, kèm vòng sinh lại. `security_gate` chứa các adapter scanner, khử trùng lặp, chấm điểm và lắp ráp báo cáo. `execution` là xương sống chạy tiến trình con với hợp đồng kết quả ổn định. `pipeline` điều phối synth, gate, diff và deploy, đồng thời giữ vết kiểm toán phê duyệt và xử lý credential. `monitoring` bao gồm CloudTrail, CloudWatch, Lambda ops-loop và đăng ký SSM cho máy on-premises. `risk_scoring` huấn luyện và đánh giá mô hình rủi ro mã nguồn. Còn `ui` và `scripts` là bảng điều khiển Streamlit cho người vận hành và giao diện dòng lệnh.
>
> Có một tính chất quan trọng hơn cả danh sách module: bảng điều khiển và dòng lệnh gọi **cùng một logic điều phối**. Một thao tác trên giao diện đồ họa đi đúng trình tự sinh mã, đánh giá, phê duyệt, triển khai — giao diện không thể đi vòng qua gate.

---

### Slide 19 — Phương pháp đánh giá (0:45)

**Nói:**
> Phần đánh giá là một chiến dịch đã đăng ký trước, và cụm từ *đăng ký trước* ở đây mang ý nghĩa thực chất.
>
> Các kịch bản, quyết định kỳ vọng của chúng và số lần lặp đã được cố định trong một đặc tả có quản lý phiên bản **trước khi bất kỳ lần chạy được báo cáo nào được thực thi**, và mọi con số thống kê ở các slide sau đều được tính từ bản ghi đã lưu bởi một chương trình phân tích duy nhất. Do đó, không có tự do lựa chọn sau khi biết kết quả xem lần chạy nào được tính.
>
> RQ1 được trả lời bằng 30 kịch bản đã khai báo trên 106 lần chạy offline, trong đó mười lần cố ý gỡ bỏ một scanner. RQ2 chạy cùng engine đó trên một node Linux on-premises, và bổ sung một nhánh đo độ phủ riêng gồm 24 kịch bản, 72 lần chạy, được thực thi hai lần. RQ3 gồm đánh giá bộ phân lớp trên tập giữ lại cộng với các ca biên có kiểm soát.
>
> Ba mươi fixture đã hiệu chỉnh — sáu fixture dải điểm và mười hai cặp đối sánh, gồm mười một lớp điểm yếu cộng một cặp đối chứng tuân thủ — với giá thời gian thực và trạng thái tài khoản thời gian thực bị tắt; trong giai đoạn thử nghiệm, chỉ riêng hai yếu tố đó đã làm một fixture *reject* nhảy từ 114 lên 119.
>
> Và một quy ước: một lần từ chối vì lý do bảo mật **không phải** là một lần chạy thất bại. Một quyết định *reject* hợp lệ, chặn được triển khai, chính là thực thi *đúng*. Chúng em báo cáo mẫu số thay vì khoảng tin cậy xuyên suốt toàn bộ kết quả.

---

### Slide 20 — RQ1: Tính phù hợp quyết định và tính đúng đắn cưỡng chế (0:50)

**Nói:**
> RQ1. Trên 106 lần chạy thuộc 30 kịch bản, mức phù hợp quyết định đạt **một trăm phần trăm** — và đạt 1.0 cho từng kịch bản riêng lẻ, nên con số tổng hợp không che giấu một kịch bản luôn sai được bù trừ bởi các kịch bản khác.
>
> Ma trận nhầm lẫn **chéo hoàn toàn**. Điều này quan trọng hơn con số phần trăm, vì một gate có thể đạt tỉ lệ đồng thuận cao trong khi vẫn dễ dãi một cách hệ thống — cho qua những thay đổi lẽ ra phải giữ lại — và một con số phần trăm đơn lẻ sẽ che mất điều đó. Ở đây không có xu hướng dễ dãi, cũng không có xu hướng chặn quá tay. Các lần chạy lặp cho kết quả giống hệt nhau: cả năm lần `cdk-reject-block` đều đúng 114 điểm; cả năm lần `ans-reject-block` đều đúng 155 điểm.
>
> Sáu bất biến cưỡng chế đều giữ ở tỉ lệ 1.00 — mọi lần chạy đều lưu bản tóm tắt, mọi lần chạy đều báo trạng thái cho từng scanner, các review chưa phê duyệt đều dừng lại, các phê duyệt đều ghi bản ghi, và các reject đều vừa chặn triển khai vừa ghi bản ghi.
>
> Hai điểm cần nói thẳng. Thứ nhất, **các mẫu số không so sánh được với nhau**: 1.00 trên mười lần chạy review-đã-phê-duyệt là một phát biểu yếu hơn nhiều so với 1.00 trên 106 lần. Bốn hàng cuối nên được đọc là "cơ chế hoạt động khi được kích hoạt", chứ không phải một ước lượng tỉ lệ lỗi. Thứ hai, mức phù hợp được đo so với một đặc tả do chính công trình này viết ra — nó cho thấy phần hiện thực thỏa mãn đặc tả của chính nó, chứ không cho thấy đặc tả chấm đúng hạ tầng thực tế.
>
> Về chi phí thời gian: gate mất trung vị 102,5 giây trên nhánh cloud, chiếm khoảng bảy mươi phần trăm tổng thời gian chạy, so với 7 giây trên nhánh on-premises. Dưới hai phút ở nhánh chậm hơn — chấp nhận được với một bước kiểm tra trước triển khai.

---

### Slide 21 — Kết quả 1: điểm số hỏng theo hướng mở (0:45)

**Nói:**
> Bây giờ là kết quả tiêu cực thứ nhất trong hai kết quả, mà chúng em cố ý đưa ra phía trước thay vì giấu đi.
>
> Mười kịch bản gỡ bỏ đúng một scanner khỏi một lần chạy vốn giống hệt nhau về mọi mặt khác. Mọi quyết định thu được đều khớp với dự đoán bằng số học, nghĩa là gate suy giảm một cách *có thể dự đoán*. Và đó chính xác là vấn đề.
>
> *(Chỉ dẫn: chỉ vào hàng Checkov ở dải review.)*
>
> Gỡ Checkov khỏi một thay đổi CDK thuộc dải review, điểm rơi từ 54 xuống 9 — quyết định trở thành **pass**. Gỡ scanner secret khỏi fixture reject của Ansible, nó mất 80 trong tổng 155 điểm.
>
> Gate đã tuân thủ đúng đặc tả ở từng hàng trong bảng này. Nhưng chính đặc tả lại cho phép một thay đổi được phát hành, chỉ vì bằng chứng đáng lẽ giữ nó lại đã không bao giờ được thu thập. **Một scanner vắng mặt và một scanner chạy nhưng không tìm thấy gì đóng góp y hệt nhau.**
>
> Bản ghi trạng thái scanner cho phép kiểm toán viên nhìn thấy điều này về sau, nhưng không có gì trong hàm quyết định phản ứng với nó. Đây là khiếm khuyết thiết kế cố hữu của mọi điểm số thuần cộng tính — không phải lỗi hiện thực. Chương 6 đề xuất một hình phạt theo mức bảo đảm để khắc phục, và chính các kịch bản suy giảm này đã sẵn sàng làm ca kiểm thử cho nó.

---

### Slide 22 — RQ2: Mức đạt các mốc kiểm tra (0:45)

**Nói:**
> RQ2 hỏi liệu cùng một mức cưỡng chế có giữ được khi vượt qua ranh giới tin cậy hay không.
>
> Sáu mươi lăm lần chạy trên nhánh Ansible: 59 lần offline, cộng thêm một nhánh sáu lần chạy thật trên một máy ảo Ubuntu 22.04 dùng một lần. Mức đạt chỉ tính các mốc **được thử** — một quyết định reject không bao giờ đi tới bước dry run, và tính đó là thất bại thì hóa ra lại phạt hệ thống vì đã hành xử đúng.
>
> Không mốc nào được thử mà thất bại, ở cả hai nhánh. Ba kết quả từ nhánh chạy thật có trọng lượng hơn cả các tỉ lệ, vì chiến dịch offline về mặt cấu trúc không thể tạo ra chúng.
>
> Thứ nhất, "apply thành công" không chỉ là mã thoát bằng không. **Chín mệnh đề kiểm tra** đọc ngược trạng thái từ máy đích — quyền thư mục, quyền tệp, shell của tài khoản dịch vụ, ràng buộc vào giao diện loopback — và chúng đối chiếu với giá trị kỳ vọng viết tường minh, chứ không phải với biến của chính fixture. Nếu đối chiếu với đúng những biến đã tạo ra trạng thái đó thì một giá trị sai vẫn sẽ được chấp nhận là đúng. Không mệnh đề nào thất bại.
>
> Thứ hai, cả ba lần chạy lặp đều ghi `changed=0`, nên trạng thái hội tụ là ổn định.
>
> Thứ ba, cả ba lần chạy `ans-reject-deploy-blocked` đều dừng tại `ansible.gate`. Không dry run, không apply — trên một máy thật, kết nối được, credential đã xác thực.
>
> Điểm cần thừa nhận: bốn hàng cuối chỉ dựa trên ba lần chạy mỗi hàng, trên một máy duy nhất từ một image mới.

---

### Slide 23 — Kết quả 2: một hàm quyết định, độ phủ phát hiện không đồng đều (0:45)

**Nói:**
> Kết quả tiêu cực thứ hai.
>
> Sẽ rất dễ đòi hỏi *sự bằng nhau về quyết định* giữa hai phía — cùng một điểm yếu thì phải cùng một dải. Nhưng đó là tính chất sai. Một luật `iptables` không phải là một security group; chúng khác nhau về phạm vi ảnh hưởng và về số lượng khiếm khuyết mà một scanner có thể nêu ra một cách chính đáng. Tệ hơn, chúng em có thể thỏa mãn yêu cầu bằng nhau một cách tầm thường bằng cách chỉnh trọng số cho tới khi các fixture khớp nhau — nhưng như vậy là đo phép chỉnh, chứ không phải đo hệ thống.
>
> Tính chất thực sự quan trọng thì yếu hơn: một lớp điểm yếu mà gate nhìn thấy ở phía này thì không được **vô hình** ở phía kia.
>
> Muốn kiểm chứng điều đó thì cần một tập lớp điểm yếu, và chính việc chọn tập đó là chỗ dễ làm hỏng một đánh giá nhất — người tự chọn danh sách có thể chọn đúng những lớp mà gate vốn đã bao phủ. Vì vậy danh sách được rút ra từ view CWE-1008 của MITRE: 223 thành viên, ba bộ lọc cơ học, còn 38 ứng viên, và mười một lớp có thể diễn đạt thành cặp đối sánh ở cả hai phía.
>
> Chúng em đo hai lần. Tại **commit đóng băng của gate**, gate gọi tên bảy trên mười một lớp ở nhánh cloud và năm ở nhánh on-premises — nhưng chỉ **ba lớp ở cả hai phía**. Bốn lớp chỉ thấy ở cloud, hai lớp chỉ thấy on-premises, hai lớp không phía nào thấy. Một gate coi hai nhánh là thay thế được cho nhau sẽ sai ở **tám trên mười một lớp**.
>
> Ở những lớp *được* gọi tên ở cả hai phía, định danh trùng nhau. Một luật tường lửa không giới hạn đều là `sg_ssh_open`, dù nó đến từ một security group hay một tác vụ iptables. Từ vựng dùng chung đó mới là kết quả thực chất, không phải các con số đếm.
>
> Và một trường hợp bỏ sót cho thấy vì sao điều đó quan trọng. Ở fixture phân quyền sai phía cloud, báo cáo **có** chứa một phát hiện của Checkov — "chính sách khóa KMS chứa principal ký tự đại diện". Scanner đã nhìn thấy. Nhưng phát hiện đó không mang category gọi tên lớp điểm yếu, nên đối với bộ khử trùng lặp, điểm rủi ro, bản ghi kiểm toán và người vận hành, nó không khác gì sự im lặng. Chúng em giữ nguyên bộ đối sánh và sửa từ vựng ở phía sinh ra phát hiện.
>
> Viết thêm chín nhóm luật đã bịt chín trên mười lỗ hổng: mười trên mười một ở cloud, mười một trên mười một ở on-premises. Hai lưu ý. Đó **không phải ước lượng độ nhạy** — nó trả lời "những lỗ hổng này có bịt được không?", chứ không phải "gate nhìn thấy được bao nhiêu?". Và một lỗ hổng được cố ý để ngỏ: một credential nhúng trong ứng dụng CDK nằm trong mã Python đa dụng, nơi không biểu thức chính quy nào tách được một secret nhúng cứng khỏi các cách viết hợp lệ dùng để *xử lý* secret. Nâng con số ở chỗ đó sẽ chỉ làm công cụ tệ đi.

---

### Slide 24 — RQ3: Năng lực đánh giá rủi ro hợp nhất (0:50)

**Nói:**
> RQ3. Trên tập giữ lại gồm 31 tệp — 16 mẫu âm, 15 mẫu dương — bộ phân lớp đạt độ chính xác 0,871 và ROC-AUC 0,879, với precision, recall và F1 đều bằng 0,867.
>
> Ma trận nhầm lẫn có bốn lỗi: hai dương tính giả và hai âm tính giả. Hai âm tính giả mới là điều đáng quan tâm về mặt vận hành — đó là những tệp được gán nhãn không an toàn nhưng nhận được đóng góp học được thấp hơn mức đáng lẽ phải có, và đó chính là chiều lỗi nguy hiểm đối với một security gate.
>
> Các hệ số lớn nhất cũng đáng nói. `total_semgrep`, `bandit_conf_medium` và `semgrep_high` dẫn đầu, cho thấy mô hình khai thác **cả hai** bộ phân tích chứ không thu về chỉ một. Đặc trưng đã được chuẩn hóa trước khi khớp mô hình, nên độ lớn là so sánh được trong phạm vi mô hình này — nhưng các đặc trưng tổng có quan hệ toán học với các đặc trưng đếm theo mức nghiêm trọng, nên hệ số mô tả mô hình, không mô tả quan hệ nhân quả.
>
> Bên cạnh đó, chúng em chạy các kiểm tra quyết định có kiểm soát tại biên: điểm 20 thì pass, 21 thì review, 80 vẫn review, 81 thì reject, và một phát hiện trùng do hai công cụ nêu ra chỉ được tính một lần. Cả năm ca đều khớp với đặc tả.

---

### Slide 25 — Hạn chế và nguy cơ đối với tính hợp lệ (0:45)

**Nói:**
> Bảy hạn chế, xin nêu thẳng.
>
> Một — các fixture do chính công trình xây dựng gate viết ra. Đăng ký trước loại bỏ tự do chọn lọc; nó không loại bỏ sự phụ thuộc đó. Và quy mô còn khiêm tốn: mười lần review được phê duyệt, mười sáu lần reject, ba lần lặp cho mỗi mốc triển khai.
>
> Hai — bằng chứng phía triển khai đến từ một máy ảo mới trên một image hệ điều hành duy nhất. Chúng em không nói được gì về tính đa dạng của máy đích, về đồng thời, hay về hỏng hóc từng phần.
>
> Ba — phạm vi. Python với Bandit và Semgrep; AWS CDK và Ansible. Không có khẳng định nào về khả năng chuyển sang ngôn ngữ, nhà cung cấp hay lớp lỗ hổng khác.
>
> Bốn — tập dữ liệu: 31 mẫu giữ lại từ một lần phân chia duy nhất, đã loại các nhóm mà công cụ không phát hiện được, và các mẫu âm là *an toàn tham chiếu*, không phải an toàn đã được kiểm chứng.
>
> Năm và sáu chính là hai kết quả hội đồng vừa nghe — điểm số hỏng theo hướng mở, và độ phủ phát hiện không đồng đều. Với ý sáu, xin lưu ý giới hạn còn lại: danh sách lớp là từ danh mục bên ngoài, nhưng fixture vẫn do chúng em viết, nên các con số chỉ giới hạn mức khớp giữa luật của gate và danh mục CWE, chứ không phải độ nhạy trên hạ tầng thực tế.
>
> Bảy — không có đường cơ sở thủ công để so sánh, và không đo công sức người vận hành, thời gian dẫn, tỉ lệ thay đổi gây lỗi hay thời gian khắc phục.

---

## Phần 5 — Kết thúc (1:30)

### Slide 26 — Kết luận (0:45)

**Nói:**
> Xin được kết luận.
>
> Hybrid cloud làm phân mảnh việc cấp phát, quản trị, phân phối và bảo mật giữa các nhóm và các bộ công cụ. Công trình này biến bảo mật thành một **quyết định vận hành tường minh và kiểm toán được** bên trong vòng đời đó, thay vì một bước rà soát diễn ra ở đâu đó bên cạnh.
>
> Một quy trình, một engine, cho cả hai phía: cùng trọng số, cùng khử trùng lặp và cùng ngưỡng chi phối cả một template CloudFormation lẫn một Ansible play. Điểm số cộng tính chuyển đầu ra của nhiều công cụ khác loại thành một quyết định duy nhất mà không đánh mất phần giải thích theo từng thành phần — thứ khiến quyết định đó hành động được.
>
> Chiến dịch đăng ký trước cho thấy gate đã hiện thực quyết định và cưỡng chế đúng như đặc tả — 106 trên 106 lần phù hợp, sáu bất biến cưỡng chế ở tỉ lệ 1.00.
>
> Nhưng nó cũng cho thấy rằng chính đặc tả cho phép phát hành khi bằng chứng bị thiếu, và rằng một hàm quyết định dùng chung, tự nó, không tạo ra sự đối xử ngang nhau khi độ phủ phát hiện khác nhau.
>
> Chúng em xem hai kết quả đó **cũng là kết quả của công trình này ngang với các con số phù hợp**. Thứ đã được chứng minh là tính đúng đắn nội tại dưới các điều kiện đã khai báo trước — không phải hiệu quả vận hành ở quy mô thực tế.

---

### Slide 27 — Hướng phát triển (0:30)

**Nói:**
> Chương trình công việc tiếp theo đi thẳng ra từ hai kết quả đó, và thứ tự chính là điều đáng nói.
>
> Thứ nhất, đóng lại lỗ hổng hỏng-theo-hướng-mở: buộc hàm quyết định tiêu thụ chính bản ghi trạng thái scanner mà nó đã ghi — bằng một hình phạt theo mức bảo đảm tỉ lệ với phần độ phủ bị thiếu, hoặc một chính sách hỏng-theo-hướng-đóng buộc chuyển sang review khi độ phủ dưới ngưỡng. Các kịch bản suy giảm hiện có đã sẵn sàng làm ca kiểm thử.
>
> Thứ hai, bịt lỗ hổng độ phủ còn lại tại gốc: cấp cho nhánh cloud một scanner secret có khả năng tách một credential nhúng cứng khỏi các cách viết hợp lệ dùng để xử lý secret — dựa trên entropy và định dạng khóa của nhà cung cấp, không phải từ khóa — cấp cho nhánh private một tín hiệu học được tương đương hoặc một trạng thái *không áp dụng* tường minh, và thay các fixture do chúng em viết bằng fixture do người độc lập soạn.
>
> Các mục ba tới sáu mở rộng bằng chứng phía triển khai, kiểm chứng mô hình trên một tập dữ liệu đa dự án lớn hơn, hiệu chỉnh điểm số theo đánh giá chuyên gia và sự cố lịch sử, và mở rộng phạm vi nền tảng.
>
> Mục một và hai là sửa chữa cho một hệ thống đã chạy được. Phần còn lại là mở rộng.

---

### Slide 28 — Cảm ơn (0:15)

**Nói:**
> Phần trình bày của chúng em đến đây là hết. Chúng em xin cảm ơn hội đồng đã lắng nghe, và rất mong nhận được câu hỏi của quý thầy cô.

*(Chỉ dẫn: giữ nguyên slide. Không chuyển sang slide dự phòng trừ khi có câu hỏi cần đến.)*

---

## Slide dự phòng — dùng khi nào

| Câu hỏi kích hoạt | Chuyển tới | Câu trả lời một dòng |
|---|---|---|
| "Vì sao chọn VPN đó? Dùng Direct Connect có được không?" | **B1 — Các phương án kết nối** | Kết nối là thành phần thay thế được; gate, chấm điểm và quản trị không đổi theo lựa chọn đó. |
| "Mô hình thực sự dựa vào đặc trưng nào?" | **B2 — Bảng hệ số đầy đủ** | Cả hai bộ phân tích đều đóng góp; các đặc trưng tổng tương quan với đặc trưng đếm theo mức nghiêm trọng, nên hệ số mô tả mô hình chứ không mô tả nhân quả. |
| "Tập dữ liệu được xây thế nào? SecurityEval có bị thiên lệch không?" | **B3 — Xây dựng tập dữ liệu** | Khoảng 150 mẫu gần cân bằng; đã loại các nhóm mà công cụ không nhìn thấy, và đó là lý do khẳng định chỉ giới hạn ở phần công cụ phát hiện được. Tập chưa lọc chỉ đạt ~0,73 độ chính xác với recall ~0,46. |
| "Khác gì so với NIST RA / CloudCAMP / thực tiễn công nghiệp?" | **B4 — So sánh** | NIST định nghĩa thành phần, không định nghĩa trình tự; CloudCAMP trừu tượng hóa nền tảng; chúng em đóng góp cơ chế chốt, khả năng truy vết và một điểm số giải thích được. Chưa có đường cơ sở thủ công định lượng. |

## Câu hỏi dự kiến không có slide dự phòng

**"Các ngưỡng có tùy tiện không?"**
> Có, theo nghĩa chúng chưa được hiệu chỉnh — đó là hạn chế số năm. Chúng được chọn sao cho các trọng số mức nghiêm trọng tạo ra dải hợp lý trên các fixture, và chúng em nêu rõ rằng hiệu chỉnh theo đánh giá chuyên gia và sự cố lịch sử là công việc cần làm tiếp. Điều mà các ngưỡng *có* đem lại là khả năng tái lập: vì dạng hàm là cộng tính và trọng số cố định, hai người bất kỳ chấm cùng một artefact sẽ ra cùng một con số.

**"Sao không dùng CVSS?"**
> CVSS chấm một lỗ hổng một cách biệt lập. Điểm số của chúng em phải kết hợp bốn chiều không cùng đơn vị — cấu hình sai, chi phí, tuân thủ thời gian thực và rủi ro mã nguồn học được — thành một quyết định triển khai duy nhất. Slide 13 chính là lập luận cho điều đó: chỉ dùng mức nghiêm trọng thì bỏ qua phạm vi ảnh hưởng và chi phí.

**"106 lần chạy có phải là quá ít không?"**
> Đúng là ít. Chính vì vậy chúng em báo cáo mẫu số thay vì khoảng tin cậy, và phân biệt rõ các bất biến được kiểm trên 106 lần với các bất biến chỉ được kiểm trên mười lần. Chiến dịch xác lập rằng cơ chế hoạt động khi được kích hoạt; nó không ước lượng tỉ lệ lỗi.

**"Sao không chỉ yêu cầu LLM viết mã an toàn ngay từ đầu?"**
> Có thể yêu cầu, và vòng sinh lại làm đúng điều đó bằng cách đưa các phát hiện vào prompt kế tiếp. Nhưng yêu cầu không phải là một biện pháp kiểm soát. Gate mới là thứ khiến kết quả kiểm chứng được, và nó áp dụng như nhau cho mã do con người viết — đó là lý do quyết định được đưa ra trên artefact đã sinh, chứ không phải trên prompt.

**"Người vận hành có thể đi vòng qua gate từ giao diện không?"**
> Không. Bảng điều khiển và dòng lệnh gọi cùng một logic điều phối — slide 18. Người vận hành có thể *phê duyệt* một quyết định review, và phê duyệt đó được ghi lại kèm danh tính của họ, nhưng không có đường nào tới bước triển khai mà không đi qua một quyết định.
