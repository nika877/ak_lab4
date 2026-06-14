(defun triangular (m) (/ (* m (+ m 1)) 2))
(defun sum-k (n k) (* k (triangular (/ (- n 1) k))))
(- (+ (sum-k 1000 3) (sum-k 1000 5)) (sum-k 1000 15))
