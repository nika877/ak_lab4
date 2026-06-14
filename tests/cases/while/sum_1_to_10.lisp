(defun sum-to (n acc)
  (progn
    (while (> n 0)
      (progn
        (setq acc (+ acc n))
        (setq n (- n 1))))
    acc))
(sum-to 10 0)
