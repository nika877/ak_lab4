(defun factorial (n result)
  (progn
    (while (> n 1)
      (progn
        (setq result (* result n))
        (setq n (- n 1))))
    result))
(factorial 5 1)
