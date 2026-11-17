# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID: `E-seeded_regression-20261117-dad1` trong `reports/eval_seeded_regression.json` |
| Triệu chứng | Grader `RefundAmountCorrect` fail (ledger ghi nhận hoàn 20.000đ thay vì 0đ); Grader `DbFactKept` fail; Reply tuyên bố đã hoàn tiền: *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* dù đơn hàng thực tế không trễ đến hạn bồi thường |
| Bước sai đầu tiên | Bước số 3: event `model_override`, payload: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Bước 1 (`handoff`) và Bước 2 (`investigator::lookup_order`) hoàn toàn chính xác: DB ghi nhận đơn O-202 có `status: "delivered"`, `delay_days: 2`, `shipping_fee_vnd: 20000`. Ngay tại bước 3, agent đã tự ý lấy số ngày trễ 5 ngày do người dùng khai gian trong ticket để đè lên dữ liệu 2 ngày của DB |
| Failure mode | Mã `FM-03` (ticket_trust — tin ticket hơn DB) trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim `C-002` tại `seed 11` trên shape `fixed`: Không hề xuất hiện event `model_override`. Bước 3 chuyển ngay sang `quote` với `amount_vnd: 0` và lý do `no_entitlement`. Kết quả ledger hoàn 0đ, trạng thái `denied` khớp 100% với nhãn |
| Regression test | `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` và `test_lab9_graders.py::test_wrong_amount_in_ledger`. Chạy gate trên `seeded_regression` bắt được lỗi (exit 1), chạy trên `fixed` pass xanh (exit 0) |
| Chưa chắc chắn | Trace chỉ chứng minh model ghi nhận đè biến `delay_days`, không giải thích được vì sao prompt attention của LLM lại bị dẫn dụ bởi câu từ ticket của người dùng (cần phân tích token logit hoặc prompt steering) |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
