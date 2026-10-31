# Ngữ cảnh làm việc và hướng đánh giá streaming

Cập nhật: 2026-10-13, Asia/Saigon. Đây là ghi chú quyết định và kế hoạch đo, không phải Results hoặc báo cáo benchmark mới.

## 1. Chat này đang làm ở đâu?

| Vai trò | Thư mục |
| --- | --- |
| Repo code chính của chat này: VSL Streaming Toolkit cho SoftwareX | `E:\Project\VSL Projects\vsl-streaming-toolkit-release` |
| Workspace mở trong IDE, tài liệu và manuscript | `E:\Paper\VSL Streaming SoftwareX` |
| App sản phẩm với UI Flutter cũ, do chat khác phụ trách | `E:\Project\VSL Projects\ver 2 - 2026-05-28 - VSL Translator` |

Các đường dẫn code tương đối bên dưới tính từ repo toolkit. File ghi chú này nằm ngay trong root repo đó. Không đồng nhất working directory của terminal với repo đang sửa.

Repo toolkit đang có thay đổi local chưa commit từ các lượt trước. Phải xem `git status` và diff trước khi tiếp tục; không reset/clean hoặc ghi đè công việc hiện có. Không sửa app sản phẩm hoặc đưa số liệu vào manuscript Results trong lượt ghi chú này.

## 2. Điều chỉnh ưu tiên: live streaming là luồng chính

Người dùng xác nhận đóng góp trọng tâm là streaming. Vì vậy:

1. **Live camera → landmarks → xử lý theo luồng → gloss events** là use case chính cần chứng minh bằng thực nghiệm.
2. **Video/trace đã lưu** phục vụ tái lập, chẩn đoán và phép so sánh kiểm soát; không thay thế bằng chứng live.
3. **Xử lý video tăng dần** là một ứng dụng của cùng streaming engine, có thể bổ sung nếu giải quyết được nhu cầu kết quả sớm và phép đo rõ ràng.

Lời khuyên trước đây đặt Video → PC làm luồng mặc định cho toàn bộ hướng nghiên cứu đã ưu tiên quá mức tính dễ tái lập. Nó phù hợp cho một bước kiểm tra orientation/extraction nhưng chưa phản ánh trọng tâm đóng góp.

Trạng thái triển khai phải được phân biệt với quyết định: bản Flutter build 6 trước đó vẫn mở mặc định Video → PC. Ghi chú này chưa đổi default, chưa build APK mới và chưa triển khai progressive video processing. Lượt triển khai tiếp theo nên đưa Live lên đầu, giữ Video/Replay trong vai trò kiểm tra và đối chứng.

## 3. Streaming hiện tại thực sự làm gì?

Code được kiểm tra trực tiếp ngày 2026-10-13:

- [`src/vsl_streaming/core.py`](src/vsl_streaming/core.py): `StreamSession.push_batch` giữ trạng thái theo frame/timestamp, xác định hoạt động của tay/cánh tay và đóng segment khi đủ điều kiện. Còn có đóng theo window, capacity, gap hoặc flush tùy mode/trạng thái.
- [`src/vsl_streaming/protocol.py`](src/vsl_streaming/protocol.py): `MessageProcessor.process` nhận segments đã đóng rồi gọi `recognizer.predict_segment`. Response được trả sau khi xử lý message; batching cũng góp phần vào thời gian đợi kết quả.
- [`src/vsl_streaming/runtime.py`](src/vsl_streaming/runtime.py): adapter preprocessing và ONNX inference cho segment.
- [`src/vsl_streaming/cli.py`](src/vsl_streaming/cli.py): `replay` đọc trace đã lưu rồi đưa từng batch qua cùng processor. Đây là replay không tự pacing theo đồng hồ camera.

Do đó đây là **thu nhận và phân đoạn tăng dần, phân loại khi segment/window đóng**. Nó chưa phải model cập nhật hidden state và đoán từ sau từng frame, cũng chưa chứng minh nhận ra ký hiệu trước khi người ký hoàn tất.

Default signing-space có `min_down_frames=4` và `min_down_ms=300`; cả hai điều kiện cần thỏa. Thời điểm UI nhận kết quả còn phụ thuộc FPS thực tế, batching, queue, inference và mạng. Không diễn giải 300 ms thành latency tổng cố định.

Trong core, thiếu pose là một quan sát inactive; mất điểm có thể tác động segmentation. Capacity/gap/flush không tự chứng minh một ký hiệu ngôn ngữ hoàn chỉnh. Cần giữ các trường hợp này trong đánh giá, thay vì loại đi để làm đẹp số liệu.

## 4. Upload video hiện tại chưa trả prediction tăng dần

Đường đang có trong [`tools/serve_video_demo.py`](tools/serve_video_demo.py), hàm `upload`:

```text
Nhận hết upload
  → lưu video gốc và tham số
  → extract_video chạy hết video, ghi frames và capture receipt
  → replay trace qua streaming core
  → gom events, ghi kết quả và trả HTTP response cuối
```

Đây là adapter xử lý tuần tự, dù bên trong replay dùng streaming state machine. Không gọi nó là trải nghiệm phát kết quả trực tiếp trong lúc trích xuất video.

[`src/vsl_streaming/video.py`](src/vsl_streaming/video.py), `extract_video`, hiện gọi `cap.read()` tuần tự, áp dụng `FrameSampler.keep`, rồi mới chạy MediaPipe trên các frame được giữ. Landmarks được tích lũy trong list và ghi sau vòng lặp. Bởi vậy:

- Target FPS có thể giảm số lần chạy detector, nhưng vòng decode hiện tại vẫn đọc tuần tự các frame.
- Core có giới hạn segment buffer không có nghĩa toàn bộ video adapter/CLI dùng bộ nhớ hằng số; chúng còn giữ trace/responses và thực hiện I/O/hash.
- Đọc upload theo chunk để lưu file không đồng nghĩa đã decode/infer trên file đang upload.

Một đường progressive có thể bổ sung sau này:

```text
Video đã upload đầy đủ
  → decode frame → sample → extract landmarks
  → feed ngay vào cùng StreamSession/MessageProcessor
  → có segment đóng thì predict và gửi event cho client
  → tiếp tục đến EOF → flush → hoàn tất artifacts
```

Muốn người dùng thấy lợi ích, backend cần chuyển events ra client ngay và UI hiển thị ngay, bằng cơ chế job/events phù hợp. Chỉ chuyển `predict` vào vòng lặp rồi giữ một HTTP response đến cuối vẫn chưa cải thiện thời điểm người dùng nhìn thấy kết quả.

Xử lý **trong khi file còn upload** là phạm vi khác: phải xác minh container, thứ tự metadata, decoder, đầu vào chưa đầy đủ và giao thức truyền. Không mặc định MP4 bất kỳ có thể decode an toàn từ mọi chunk upload. Trước mắt có thể đo progressive processing sau khi upload hoàn tất.

## 5. Trả kết quả sớm hơn khác với hoàn tất nhanh hơn

Streaming có thể phát kết quả của ký hiệu đầu trước khi xử lý hết phần còn lại của video. Nó vẫn cần decode/sampling/extraction và cần các quan sát đủ để xác nhận ranh giới ký hiệu.

Kiểm tra tay lên/xuống trong core là phép tính hình học trên landmarks đã có; detector pose/hands và decode là các công đoạn riêng. Phải profile từng công đoạn, không kết luận kiểm tra tay là nút thắt chỉ từ cảm giác chờ lâu.

Nếu hai đường dùng cùng N frame, cùng detector và cùng số segment, tổng công việc có thể tương tự. Pipeline overlap, warm model, giảm sao chép hoặc I/O có thể cải thiện thời gian tổng; tranh chấp CPU, queue hoặc overhead cũng có thể làm nó chậm hơn. Chưa có phép đo mới để khẳng định hướng nào nhanh hơn.

Các điều chỉnh FPS/resolution/model có thể đổi cả tốc độ và chất lượng, nên không được gộp vào so sánh scheduling rồi quy mọi khác biệt cho streaming.

## 6. Phép so sánh cần làm

### A. Đối chiếu downstream trên cùng trace

Dùng đúng một chuỗi canonical landmarks, giữ nguyên thứ tự, timestamp, null, model/labels/profile, segmentation config và flush cuối. So sánh replay với gửi incremental qua WebSocket, kể cả các batch size khác nhau trong giới hạn protocol.

So sánh events, ranh giới, closure reason, status, nhãn/scores, rejected events và dữ liệu đã được ACK. Không so thời gian inference bằng phép bằng tuyệt đối. Mục đích là kiểm chứng đường truyền/processor; trace trích sẵn không đo detector, độ chính xác ký hiệu hay latency camera.

### B. Video xử lý sau khi trích hết so với video xử lý tăng dần

| Điều kiện | Đầu vào và cách chạy | Câu hỏi |
| --- | --- | --- |
| B1: staged/buffered | Decode/extract hết, sau đó dùng cùng segmentation/model để xử lý trace | Mốc đối chứng rõ ràng của luồng hiện tại |
| B2: incremental | Decode/extract cùng các frame, feed vào cùng processor ngay, phát events khi có | Có nhận kết quả sớm hơn không; tổng thời gian và bộ nhớ thay đổi thế nào? |

Đây là đối chứng cách tổ chức pipeline, không phải tuyên bố mọi phần mềm offline đều kém hơn. Không cố tình làm B1 đọc/trích lại prefix nhiều lần, dùng model chậm hơn hoặc giữ cấu hình thread bất lợi để tạo speedup.

Giữ cùng video bytes/hash, timestamp policy, rotation/mirror, detector assets/options/history, selected source indices, profile, model, segmentation, provider/threads và chính sách logging/artifacts. Dùng recognizer đã khởi tạo cho cả hai khi đo warm; báo cold startup riêng. Đối chiếu trace và events để phát hiện sai khác đầu vào trước khi diễn giải timing.

Tách chạy **unpaced, nhanh nhất có thể** khỏi **replay theo tốc độ nguồn 1×**. Không gộp thời gian sleep của replay vào tốc độ xử lý thuần. Luân phiên thứ tự chạy, lặp trên cùng clip và báo số clip độc lập thay vì coi mỗi lần lặp là một người ký mới.

### C. Live end-to-end trên điện thoại thật — thí nghiệm trọng tâm

Camera thật → Android extraction → transport → server segmentation/inference → UI. Ghi actual FPS, missingness, admitted/ACK/drop/uncertain, batching/queue, closure reason, latency và tài nguyên phù hợp. Ghi model/config/runtime/thiết bị/mạng cho mỗi run.

Thử camera thật khác một video trên PC ở cả detector/runtime, nguồn hình, sampling và vị trí tính toán. Có thể báo hai cấu hình triển khai cạnh nhau, nhưng không quy chênh lệch chỉ cho streaming. Giữ phép B để cô lập cách xử lý, phép A để cô lập downstream và phép C để chứng minh vận hành live.

Để đo recognition/segmentation, cần video tham chiếu có nhãn người ký đã được kiểm tra và cách đồng bộ ranh giới với trace. Nếu thêm ghi video đồng thời, phải đo overhead của chính việc ghi; không lờ đi ảnh hưởng đó. Một live trace không có video tham chiếu vẫn dùng kiểm tra transport, nhưng không tự cung cấp ground truth về động tác.

### D. Phân loại clip đã cắt sẵn — đối chứng phụ nếu cần

Nếu “predict bình thường” là nhận một clip đã chứa đúng một ký hiệu, hãy đặt tên rõ là isolated/oracle-segment classification. Nó bỏ qua nhiệm vụ tìm ranh giới. Có thể dùng để chẩn đoán model/preprocessing, nhưng không đem accuracy/timing của nó so ngang với luồng tự tìm nhiều ký hiệu mà không nêu khác biệt nhiệm vụ.

Nếu “predict bình thường” là pipeline legacy dùng Holistic hoặc preprocessing khác, báo thành đối chứng hệ thống riêng. Không gọi đó là so sánh chỉ thay offline bằng streaming.

## 7. Chỉ số và đồng hồ

- Time to first event: từ mốc bắt đầu được quy định trước đến khi client nhận event dự đoán đầu tiên, không phải ACK rỗng. Báo clip không có event; không loại lặng lẽ khỏi thống kê.
- Completion time: đến lúc xử lý/flush/kết quả cuối hoàn tất, không chỉ đến EOF hoặc lúc request được ACK.
- Thời gian theo từng stage: upload, decode/extract, segmentation, preprocess/inference, transport, delivery; tách cold startup và I/O khi diễn giải.
- Real-time factor cho video unpaced: thời gian xử lý / thời lượng nguồn, kèm ranh giới đo. RTF của file không tự chứng minh latency live.
- Event latency: cần end-of-sign tham chiếu và thời điểm nhận event cùng clock domain hoặc có đồng bộ và sai số được báo. `end_ms` của emitted segment có thể chứa debounce tail; không dùng nó như ground-truth end-of-sign.
- FPS thực đo, chất lượng landmarks, queue/drop, peak memory/CPU và tính đầy đủ của artifacts.
- Khi có nhãn: detection precision/recall/F1 theo temporal overlap, lỗi ranh giới, gloss/sequence errors và số segment thừa/thiếu/rejected. Dùng [`docs/EVENT_EVALUATION.md`](docs/EVENT_EVALUATION.md), không dùng prediction làm annotation.

Không lấy timestamp phone trừ timestamp PC khi chưa có cơ chế đồng bộ. Không cộng các p95 thành p95 tổng. Không đổi threshold trên test để làm đẹp kết quả; chọn trên validation rồi khóa.

## 8. Bằng chứng hiện có và phần chưa làm

Báo cáo engineering trước đó: [`artifacts/device-test/flutter-minimal-20261012-02/REPORT_VI.md`](artifacts/device-test/flutter-minimal-20261012-02/REPORT_VI.md).

Các lượt đã ghi nhận gồm live smoke và canonical replay. Đây là bằng chứng kỹ thuật có phạm vi, chưa phải pilot nhận dạng có ground truth. Bản báo cáo ghi observed live output khoảng 7.15 FPS so với target 15; không coi target là FPS đạt được. CameraX KEEP_ONLY_LATEST không cho phép suy ra mọi frame camera đều đã được xử lý từ số ACK.

Chưa chạy phép B1/B2 hoặc benchmark live có nhãn trong lượt ngày 2026-10-13 này. Chưa xác lập detector/training-extractor equivalence. Tham khảo [`docs/FLUTTER_CAPTURE_COMPATIBILITY.md`](docs/FLUTTER_CAPTURE_COMPATIBILITY.md) và [`docs/REMEASUREMENT_PLAN.md`](docs/REMEASUREMENT_PLAN.md).

## 9. Thứ tự tiếp theo

1. Đưa Live lên vị trí chính trong app demo và hướng dẫn; giữ Video/Replay làm công cụ đối chiếu. Đây là công việc tiếp theo, chưa được thực hiện bởi file ghi chú này.
2. Kiểm tra người thật qua Live, lưu trace/receipt/server events và kiểm tra chất lượng đầu vào. Chưa cần thu toàn bộ 400 từ.
3. Xác nhận lại cùng-trace replay/transport agreement cho phiên đó.
4. Làm harness B1/B2 trên cùng nguồn video, với progressive event delivery và timing hooks đúng ranh giới. Ghi rõ quyết định triển khai và kiểm tra hồi quy trước khi đo.
5. Chốt pilot live có nhãn, cách quay tham chiếu/đồng bộ và cấu hình extractor/checkpoint; sau đó mới đo recognition, segmentation và latency thực tế.
6. Chỉ dùng các phép đo đã hoàn tất và có artifact để viết Results.

Lượt hiện tại chỉ đọc code và tạo file ngữ cảnh này. Không sửa core, APK, repo sản phẩm hoặc manuscript; không chạy benchmark mới và không khẳng định speedup/accuracy mới.

## 10. Checkpoint và ý tưởng video song song — 2026-10-13

Theo yêu cầu lưu trạng thái, đã tạo [checkpoint source](artifacts/checkpoints/20261013-before-parallel-video/README_VI.md): commit nền d9239374299f8b3390843d94e0910f64152db434 cùng 44 file local thay đổi, diff và manifest SHA-256. Archive được kiểm tra hash từng entry. Model/video/APK và artifacts ignored vẫn ở chỗ cũ; đây không phải full backup.

Đã bổ sung [nghiên cứu và thiết kế thử nghiệm video song song](docs/PARALLEL_VIDEO_RESEARCH_VI.md), đối chiếu SPOTER, TwoStream-SLR, segmentation bằng temporal model, online SLR và handshape-aware boundaries công bố đến năm 2026.

Quyết định: tách tối ưu scheduling khỏi cải thiện phân đoạn. Profile từng stage và làm đối chứng incremental với extractor liên tục trước; chỉ thử worker/chunk có overlap nếu nút thắt và lợi ích đo được biện minh. Tracker có lịch sử nên chia chunk có thể đổi landmarks; overlap không bảo đảm parity. Boundary model cần dữ liệu/nhãn và validation riêng, không thể có chỉ bằng thêm nhiều worker.

Live tiếp tục là luồng trọng tâm. Đề xuất video song song chưa được triển khai hoặc benchmark; không đổi APK, model/core hay Results trong lượt lưu trạng thái và nghiên cứu này.
