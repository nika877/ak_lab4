(defun sum-multiples (n acc)
  (if (== n 0)
      acc
      (sum-multiples (- n 1)
                     (+ acc (if (or (== (mod n 3) 0)
                                    (== (mod n 5) 0))
                                n
                                0)))))
(sum-multiples 10 0)
