(defun double (x) (* x 2))
(defun add-ten (x) (+ x 10))
(defun compose (x) (add-ten (double x)))
(compose 5)
