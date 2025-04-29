from(bucket: "tlb")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) =>
        r._measurement == "tlb_flush" and
        r._field       == "reason_str" and   // field name
        r.comm         == "code" and
        r.cpu          == "0")
  // promote field value to a tag
  |> map(fn: (r) => ({ r with reason_str: r._value, _value: 1 }))
  |> group(columns: ["reason_str"])         // group by the new tag
  |> aggregateWindow(every: 1s, fn: sum, createEmpty: false)
  |> rename(columns: {_value: "flushes"})
  |> yield(name: "flushes_per_sec")
