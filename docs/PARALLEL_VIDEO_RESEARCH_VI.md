# Đề xuất xử lý video song song và phân đoạn ký hiệu

Ngày rà soát: 2026-10-13. Trạng thái: nghiên cứu và thiết kế thí nghiệm; chưa triển khai worker pool, chưa train boundary model và chưa đo speedup.

## 1. Mốc hiện tại đã được lưu

- Repo triển khai: E:\Project\VSL Projects\vsl-streaming-toolkit-release.
- Workspace manuscript: E:\Paper\VSL Streaming SoftwareX.
- App sản phẩm có UI cũ nằm ở repo riêng: E:\Project\VSL Projects\ver 2 - 2026-05-28 - VSL Translator.
- [Ngữ cảnh và kế hoạch hiện hành](../WORKING_CONTEXT_VI.md).
- [Checkpoint trước nghiên cứu này](../artifacts/checkpoints/20261013-before-parallel-video/README_VI.md): commit nền d9239374299f8b3390843d94e0910f64152db434 cộng archive 44 file local thay đổi. Đây là checkpoint source, không phải bản sao toàn bộ model/video/APK/môi trường.
- Không sửa runtime, APK, repo sản phẩm hay Results trong lượt nghiên cứu này.

Live vẫn là luồng trọng tâm của toolkit streaming. Video có sẵn là đầu vào hữu ích để tái lập, đối chứng và thử tối ưu; chưa chốt thành contribution mới về multi-agent recognition.

## 2. Kết luận thiết kế

Ý tưởng chia việc để video hoàn tất nhanh hơn là khả thi về kỹ thuật. Tuy nhiên cần tách hai giả thuyết:

1. Scheduling song song có giảm thời gian xử lý với chất lượng giữ nguyên không?
2. Mô hình có ngữ cảnh có tìm ranh giới ký hiệu tốt hơn heuristic hiện tại không?

Nhiều worker không tự làm bộ phân đoạn thông minh hơn. Nên bắt đầu bằng các worker tính toán có đầu vào/đầu ra xác định, một bộ điều phối giữ thứ tự thời gian và một bước hòa giải ở vùng chồng lấn. Chưa có lý do kỹ thuật để dùng nhiều LLM trao đổi bằng ngôn ngữ tự nhiên cho nhiệm vụ landmarks/ranh giới này.

Live cần xử lý quan sát theo quan hệ nhân quả: không dùng các frame tương lai chưa tới. Điều đó không buộc mọi frame camera phải qua toàn bộ model. Có thể lấy mẫu, giới hạn queue và bỏ frame theo chính sách được ghi lại; đổi sampling phải kiểm tra ảnh hưởng chất lượng. Video đã có sẵn có thể dùng ngữ cảnh tương lai và scheduling khác, nên không so latency hai chế độ mà bỏ qua khác biệt này.

## 3. Paper nhận dạng ký hiệu đang làm gì?

Đây là rà soát có mục tiêu, không phải bảng xếp hạng SOTA hay systematic review.

| Nhóm | Cơ chế trong nguồn gốc | Hàm ý cho toolkit |
| --- | --- | --- |
| Isolated sign recognition | SPOTER dùng chuỗi pose của một ký hiệu để phân loại. [Paper WACV Workshops 2022](https://openaccess.thecvf.com/content/WACV2022W/HADCV/html/Bohacek_Sign_Pose-Based_Transformer_for_Word-Level_Sign_Language_Recognition_WACVW_2022_paper.html), [code tác giả](https://github.com/maty-bohacek/spoter). | Clip đúng ranh giới là giả định đầu vào; classifier không tự chứng minh khả năng tách chuỗi liên tục. |
| Continuous SLR với CTC | TwoStream-SLR kết hợp RGB và keypoint heatmaps, dùng CTC để học chuỗi gloss từ giám sát ở mức chuỗi. [NeurIPS 2022](https://papers.neurips.cc/paper_files/paper/2022/hash/6cd3ac24cdb789beeaa9f7145670fcae-Abstract-Conference.html), [bản toàn văn](https://arxiv.org/html/2211.01367). | Không cần quy tắc hạ tay giữa hai gloss. CTC alignment không phải annotation ranh giới vật lý; khả năng online còn phụ thuộc encoder và lookahead. |
| Learned boundary detection | Renz và cộng sự dùng đặc trưng 3D CNN và temporal convolutional networks để dự đoán ranh giới. [ICASSP 2021, trang nhóm tác giả](https://www.robots.ox.ac.uk/~vgg/research/signsegmentation/icassp.html). | Tìm ranh giới là bài toán học riêng; phải có dữ liệu và kiểm chứng phù hợp với VSL. |
| Handshape-aware boundaries | Zhao và cộng sự kết hợp đặc trưng cơ thể/chuyển động và cấu hình bàn tay để tìm đoạn rồi nhận dạng. [LREC SignLang 2026](https://www.sign-lang.uni-hamburg.de/lrec/pub/26014.html). | Ý tưởng nhiều nguồn tín hiệu cùng xác định ranh giới đã có tiền lệ; không thể coi worker pool là novelty nhận dạng. |
| Online continuous recognition | Zuo và cộng sự dùng alignment từ model continuous, huấn luyện classifier có xử lý nền/chuyển tiếp, chạy cửa sổ trượt và hậu xử lý. [EMNLP 2024](https://aclanthology.org/2024.emnlp-main.619/). | Chạy classifier trên nhiều cửa sổ cần thích nghi cách huấn luyện; không chỉ áp model isolated hiện có vào mọi cửa sổ. |

Gloss là nhãn định danh ký hiệu trong dữ liệu, không mặc định tương ứng một-một với từ tiếng Việt trong câu dịch.

Câu trả lời cho “có phải từng frame để bắt tay lên xuống không?”: model vẫn cần quan sát video hoặc các đặc trưng được trích từ video, nhưng không nhất thiết dùng quy tắc tay lên/xuống, cũng không nhất thiết tính mọi công đoạn tuần tự từng frame. Tensor của nhiều frame/cửa sổ có thể được xử lý bằng phép toán song song, tùy kiến trúc và phần cứng.

Hai ký hiệu liên tiếp có thể không có khoảng hạ tay; một ký hiệu có thể chứa nhiều pha chuyển động và giữ tay. Do đó, hoạt động của tay và ranh giới ngôn ngữ là hai đại lượng khác nhau. Các hướng học ranh giới hoặc nhận dạng chuỗi ở trên chính là những đối chứng cần cân nhắc.

Không chuyển số accuracy từ ASL/BSL/DGS sang VSL. Không dùng kết quả chỉ trên đoạn đã khớp ground truth để đại diện toàn bộ chuỗi dự đoán. Bản MHB preprint có phạm vi đánh giá nhận dạng được lọc theo đoạn khớp và lớp đủ mẫu; khi tham khảo cần đọc điều kiện đó, không chỉ con số top-1. [MHB, phần 3.5 và 4.3](https://arxiv.org/html/2511.19907).

## 4. Đối chiếu code hiện tại

Các kết luận sau dựa trên code local đã đọc, không suy từ paper:

- [video.py](../src/vsl_streaming/video.py): decode tuần tự, lấy mẫu rồi gọi Pose/Hand Landmarker ở chế độ VIDEO. Tích lũy trace đầy đủ trước khi ghi kết quả extraction.
- [core.py](../src/vsl_streaming/core.py): StreamSession giữ trạng thái theo thứ tự; signing_space là heuristic hình học của vai/khuỷu/cổ tay và độ hiện diện landmarks, có debounce. Segment còn có thể đóng do window/capacity/gap/flush. Không phải learned linguistic segmentation.
- [protocol.py](../src/vsl_streaming/protocol.py): chỉ gọi recognizer sau khi segment đóng; event trả sau xử lý message. Chưa có early prediction liên tục trong một ký hiệu đang mở.
- [serve_video_demo.py](../tools/serve_video_demo.py): nhận hết upload, trích hết trace, replay rồi trả một response cuối. Đường này chưa phát prediction tăng dần ra UI.
- [bundle.py](../src/vsl_streaming/bundle.py) và [runtime.py](../src/vsl_streaming/runtime.py): hợp đồng input hiện tại có batch dimension 1; predict_segment gọi model cho một đoạn. Muốn minibatch phải kiểm tra export, profile và validation, không chỉ xếp chồng tensor.
- Model nhiều lớp hiện có chưa cung cấp một boundary/background model đã được xác thực cho cửa sổ tùy ý. Softmax cao trên đoạn chuyển tiếp không chứng minh đoạn đó là một ký hiệu hoàn chỉnh.

Quy tắc hình học trên landmarks không đồng nghĩa với chi phí detector. Phải đo decode, pose, hands, segmentation, preprocessing/inference và I/O riêng trước khi quyết định tối ưu phần nào.

MediaPipe VIDEO/LIVE dùng tracking để giảm số lần chạy palm detector; tracking phụ thuộc quan sát trước đó. Vì vậy chia xen kẽ frame sang các instance sẽ đổi lịch sử tracker. [Tài liệu Hand Landmarker của Google](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python).

Đề xuất kỹ thuật từ đặc tính đó: nếu thử chia chunk, mỗi worker cần instance riêng, timestamp đúng thứ tự và phần chạy trước vùng được giữ lại để khởi tạo tracking. Overlap có thể giảm lỗi chỗ nối nhưng chưa bảo đảm landmarks bằng kết quả chạy liên tục. Nếu thay đổi đầu ra, phải ghi thành capture profile khác và đánh giá; không gọi đó là tối ưu scheduling thuần.

## 5. Thứ tự thử nghiệm được đề xuất

### P0: Profile trước

Dùng một nhóm clip có hash, cùng frame selection và cấu hình. Đo thời gian mỗi stage, khởi tạo model, bộ nhớ, CPU, số frame/segment và thời điểm client thật sự nhận prediction đầu tiên.

Phân biệt time to first event với completion time. Ví dụ giả định, không phải số đo VSL: nếu segmentation chỉ chiếm 5% thời gian, làm nó tức thời cũng chỉ cải thiện tối đa khoảng 1/0.95 = 1.05 lần khi các công đoạn khác không đổi.

### P1: Pipeline tăng dần, giữ lịch sử extractor

Decode/extract theo đúng thứ tự -> đẩy frame vào cùng StreamSession -> inference đoạn đã đóng -> phát event tới client ngay. Queue phải hữu hạn, có backpressure/cancellation và flush cuối rõ ràng.

Đây là đối chứng trước khi thêm worker. Nó có thể cải thiện thời điểm thấy kết quả mà chưa chắc giảm thời gian hoàn tất.

Nếu inference các đoạn đã đóng là nút thắt, có thể thử worker xử lý các đoạn độc lập và một bộ trả kết quả theo thứ tự segment. Phải quản lý session/thread/memory và không sửa nhầm state của StreamSession. Batch dimension 1 không cấm nhiều job độc lập, nhưng không phải hỗ trợ minibatch có sẵn.

### P2: Chỉ thử chunk song song nếu extraction là nút thắt

Thiết kế thực nghiệm:

    Video gốc + chỉ số frame/timestamp toàn cục
        -> decoder/lịch lấy mẫu có thể tái lập
        -> các chunk gồm vùng chính + ngữ cảnh chồng lấn
        -> worker extractor riêng cho từng chunk
        -> sắp lại theo thời gian, mỗi frame chính có một chủ sở hữu
        -> một bộ phân đoạn trên timeline đã ghép
        -> recognizer + kết quả theo thứ tự

Ranh giới chunk là ranh giới tính toán, không được tự coi là ranh giới ký hiệu. Bản đầu nên ghép landmarks về timeline toàn cục rồi chạy một segmenter để ký hiệu có thể đi qua chỗ nối. Nếu sau này mỗi worker còn dự đoán ranh giới, phải ghép điểm số/ngữ cảnh trước khi chốt đoạn.

Các điều kiện cần giữ:

1. Chỉ số frame nguồn và timestamp toàn cục không mất, trùng hoặc đảo thứ tự; không đổi sampling vì chia chunk.
2. Vùng chồng lấn phục vụ ngữ cảnh; output chính có quy tắc sở hữu xác định. Không lấy trung bình landmarks mù quáng khi hand identity khác nhau.
3. Lưu rõ dấu hiệu đoạn mở bên trái/phải nếu thực hiện segmentation cục bộ. Không flush ở mọi mép chunk rồi coi các đoạn đó là ký hiệu hoàn chỉnh.
4. Ghép theo thời gian và provenance; không gộp hai sự kiện chỉ vì cùng nhãn. Hai ký hiệu giống nhau liên tiếp phải được giữ nếu thực sự được ký hai lần.
5. Kích thước overlap phải chọn bằng validation, không giả định cố định một giây là đủ. Tracker có thể mang lịch sử dài hơn overlap.
6. Chỗ nối không chắc chắn có thể chạy lại với ngữ cảnh rộng hơn; tính cả chi phí này vào timing.
7. Giới hạn worker/queue/bộ nhớ. Sao chép ảnh và nhiều detector cùng dùng CPU có thể xóa hết lợi ích.
8. Decode song song phải xử lý keyframe/seek/timestamp và rotation đúng; chia ở frame bất kỳ không miễn phí. Giai đoạn đầu nên tránh đồng thời đổi cả decoder lẫn tracker.

Chạy nhiều video độc lập song song là phép tối ưu dễ bảo toàn lịch sử mỗi video hơn; nó tăng throughput cả lô, không tự làm một video đơn lẻ nhanh hơn.

### P3: Boundary model là nhánh nghiên cứu riêng

Chỉ mở khi có lỗi phân đoạn thật đã được gán nhãn và dữ liệu đủ cho train/validation/test. Có thể khảo sát temporal model trên pose, motion và handshape; chưa chọn kiến trúc chỉ từ tên paper.

Bộ 400 nhãn isolated và khả năng chạy classifier không tự cung cấp annotation ranh giới liên tục. Pilot nhỏ có thể phát hiện lỗi và đánh giá sơ bộ, không mặc định đủ để huấn luyện boundary model tổng quát.

Giữ baseline heuristic và baseline pipeline tăng dần. Không thay model, extractor, sampling và scheduler cùng lúc rồi quy mọi lợi ích cho song song.

## 6. Phép thử có thể bác bỏ ý tưởng

| So sánh | Giữ cố định / thay đổi | Bằng chứng cần thu |
| --- | --- | --- |
| Cùng trace, inference tuần tự so với worker | Giữ landmarks, đoạn, model, provider/config; đổi scheduling | Đủ sự kiện, đúng thứ tự, nhãn/scores trong dung sai định trước, lỗi/cancellation rõ ràng |
| Video staged so với incremental | Giữ video, extractor/history, sampling, model; đổi thời điểm feed/delivery | Trace/event agreement, first event, completion, peak memory |
| Extract liên tục so với chia chunk | Giữ video/assets/options; đổi lịch sử theo chunk và overlap có ghi nhận | Coverage, landmark discrepancy/missingness/hand assignment, sai khác ranh giới và nhận dạng |
| Heuristic so với learned boundaries | Giữ input/features và split độc lập; đổi segmenter | Boundary/segment metrics và toàn bộ chuỗi nhãn, kể cả đoạn thừa/thiếu |

Thử worker 1/2/4 theo tài nguyên thực có; báo cả trường hợp chậm hơn. Đo cold startup riêng, warm runs luân phiên, tổng wall time đến kết quả cuối và RTF chạy nhanh nhất có thể. Không đưa sleep của replay 1x vào tốc độ tính toán. Ghi upload riêng và cả thời gian end-to-end người dùng chờ.

Nhóm clip kiểm tra cần có: ký hiệu đi qua chỗ nối, hai ký hiệu giống nhau liên tiếp, chuyển ký hiệu mà tay vẫn giơ, ngừng tay giữa một ký hiệu, ký nhanh, che khuất/tay mất điểm, clip không ký và video dọc có metadata rotation.

Khi có ground truth, báo boundary precision/recall/F1 với dung sai đã chốt, segment overlap, và lỗi chuỗi gloss gồm thay thế/xóa/chèn. Không chỉ tính accuracy trên các đoạn sống sót qua bước lọc. Tham khảo [EVENT_EVALUATION.md](EVENT_EVALUATION.md).

Chốt trước mức cải thiện thời gian đáng triển khai, ngân sách bộ nhớ và biên chất lượng cho phép trên validation. Nếu speedup nhỏ, tài nguyên tăng quá nhiều hoặc lỗi chỗ nối không đạt yêu cầu, giữ extractor liên tục và pipeline tăng dần. Không mở rộng training chỉ để cứu một giả thuyết chưa được chứng minh.

## 7. Quyết định hiện tại

Lưu ý tưởng thành nhánh thử nghiệm có kiểm soát; chưa đưa multi-agent vào tuyên bố contribution. Công việc kế tiếp hợp lý là thêm profiling/harness nhỏ cho P0/P1, sau đó dùng kết quả để quyết định có đáng làm P2 hay P3.

Live end-to-end, hợp đồng landmarks/model, event delivery, khả năng tái lập và đánh giá có ground truth vẫn là mục tiêu chính. Source checkpoint, tài liệu nghiên cứu và thiết kế đối chứng đã được chuẩn bị; chưa có speedup hay kết quả nhận dạng mới để viết Results.
