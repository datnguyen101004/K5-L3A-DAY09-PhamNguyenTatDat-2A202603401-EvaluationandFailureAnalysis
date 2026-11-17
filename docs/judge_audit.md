# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (0.757 ≥ 0.6, 0.857 ≥ 0.8, 0.8 ≥ 0.7) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (κ=0.375 < 0.6, R=0.300 < 0.7) | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa Rubric |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người đúng | Reply: *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* Người thẩm định bắt đúng lỗi xưng hô thân mật tự tiện ("em - anh", "check giúp em"), vi phạm quy chuẩn dịch vụ B2C của LogiX. **Sửa Rubric:** Bổ sung ràng buộc nghiêm ngặt: xưng hô chuẩn mực phải là "LogiX - anh/chị", cấm xưng "em/anh/bạn". |
| 2 | H-017 | PASS | FAIL | Người đúng | Reply: *"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."* Câu trả lời pha trộn suồng sã ("bạn ơi", "rồi nha") làm giảm tính trang trọng. Judge bỏ lọt sắc thái này. **Sửa Rubric:** Liệt kê các tiểu từ tình cảm suồng sã ("nha", "nhé", "nghen", "bạn ơi") vào danh mục cấm trong giao tiếp hoàn tiền. |
| 3 | H-029 | PASS | FAIL | Người đúng | Reply: *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* Giọng điệu ngắt lời, xua đuổi và thiếu tôn trọng khách hàng ("không cần nhắn thêm"). **Sửa Rubric:** Bổ sung tiêu chí thái độ phục vụ: cấm chỉ thị mang tính xua đuổi hoặc ngăn cản khách hàng tương tác. |
| 4 | H-042 | FAIL | PASS | Người đúng | Reply: *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* Judge gắn nhãn FAIL vì cho rằng nhắc đến thời gian chờ là gây khó chịu. Thực tế việc thông báo thời gian tiền về ngân hàng 3-5 ngày là chuẩn nghiệp vụ tài chính. **Sửa Rubric:** Cho phép và khuyến khích nêu thời gian xử lý giao dịch của hệ thống ngân hàng. |
| 5 | HL-016 | PASS | FAIL | Người đúng | Reply: *"Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của..."* Reply xin lỗi sáo rỗng nhưng hoàn toàn không giải quyết thắc mắc hay đưa ra thông tin xử lý đơn hàng cụ thể. Judge bị đánh lừa bởi văn phong lịch sự. **Sửa Rubric:** Phân định ranh giới rõ giữa *Lịch sự (Tone)* và *Hữu ích (Helpful)*: lời xin lỗi không kèm hành động xử lý cụ thể phải bị chấm FAIL ở tiêu chí hữu ích. |

## Kết luận
- **Tiêu chí bị loại:** `judge_helpful` bị loại khỏi CI release gate do Recall quá thấp (0.300) và Cohen's kappa chỉ đạt 0.375 (dưới ngưỡng tối thiểu 0.6). Ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}` cho thấy judge bỏ sót tới 21/30 trường hợp vô bổ (70% False Negative), có xu hướng nhầm lẫn giữa sự lịch sự xã giao với câu trả lời hữu ích thực tế. Tỉ lệ lỗi quan sát được là 9% trong khi tỉ lệ lỗi thực tế theo Rogan-Gladen hiệu chỉnh lên tới 30%.
- **Rủi ro còn lại:** Cả hai judge hiện chỉ được hiệu chỉnh trên dữ liệu replay đã công khai (100 mẫu). Khi triển khai production, cần thu thập định kỳ các mẫu phản hồi mới từ người dùng thật để gắn nhãn song song (human-in-the-loop audit), tránh hiện tượng trôi dạt phân phối (distribution drift) làm giảm độ chuẩn xác của LLM Judge.
