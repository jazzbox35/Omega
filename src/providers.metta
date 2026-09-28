;----------------;
; Default router ;
;----------------;

;(= (flatten ()) ())
;(= (flatten $x)
;    (if (== 1 (size-atom $x))   
;      ($x)
;      (let $rest (cons-atom (flatten (car-atom $x)) (flatten (cdr-atom $x))) $rest)
;    )
;)


; These function load the prompt into a &temp atomspace for very fast search and deletion.
(= (create_temp_atoms $prompt_list)
   (if (== $prompt_list ())
      True
      (let*
        (
        ($atom (car-atom $prompt_list))
        ($_ (add-atom &temp (prompt_atom $atom)))
        ($_ (log INFO "atom>" $atom))
        )
        (create_temp_atoms (cdr-atom $prompt_list)))))

(= (delete_temp_atoms)
   (collapse (match &temp (prompt_atom $x) (remove-atom &temp (prompt_atom $x)))))

(= (lookup_term $term)
    (match &temp (prompt_atom $atom) 
                        (if (== $atom $term)
                           1
                           (empty))))

; The default_router can be refined to look for a variety of conditions and keywords.
; The MeTTa code should be pretty fast
(= (default_router $prompt $max_tokens $reasoning_mode)
   (let* (
         ($prompt_list (split_string $prompt " " " "))
         ($_ (create_temp_atoms $prompt_list))
         ($found_complexity 
               (collapse (lookup_term 
                    (superpose 
                         ("ALERT_FAILED" "premium_model")))))
         ($_ delete_temp_atoms)
         )
         (if (== $found_complexity ())
                           economy_model
                           premium_model)))

(= (llmProviderStart $provider)
   (py-call (providers.llmProviderStart $provider)))

;-------------------------------------------------------------------------------
;  Prototype -- $router is the name of the router passed. This case statement can 
;     be expanded for other modules probably to be located in a new 'routers' directory.
;-------------------------------------------------------------------------------
(= (llmProviderChat $prompt $max_tokens $reasoning_mode $router)
   (case $router
      (
      (default
         (let $tier (default_router $prompt $max_tokens $reasoning_mode)
          (py-call (providers.llmProviderChat $prompt $max_tokens $reasoning_mode $tier))))
      ($_otherwise (py-call (providers.llmProviderChat $prompt $max_tokens $reasoning_mode)))
      )))