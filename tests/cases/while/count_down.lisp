(defun count-down (n)
  (progn (while (> n 0) (setq n (- n 1))) n))
(count-down 5)
