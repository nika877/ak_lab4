(defun test (x)
  ((lambda (f) (progn (setq x 42) (f)))
   (lambda () x)))
(test 0)
