((lambda (s n i j a b)
   (progn
     (setq n (string-length s))
     (setq i 0)
     (while (< i n)
       (progn
         (setq j 0)
         (while (< j (- n 1))
           (progn
             (setq a (string-ref s j))
             (setq b (string-ref s (+ j 1)))
             (if (> a b) (string-set! s j b) 0)
             (if (> a b) (string-set! s (+ j 1) a) 0)
             (setq j (+ j 1))))
         (setq i (+ i 1))))
     (print s)))
 (input) 0 0 0 0 0)
