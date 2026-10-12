;----------------;
; Default router ;
;----------------;
;
; The simple default router looks for single terms in tool results and user messages and
; returns one catalogue entry (ADR-0001): the configured model, or premium_model on the
; same provider. It also checks other criteria as defined herein.
; If a complexity condition is found, premium_model is returned, else the configured model.
; The keywords (router_escalate_keywords) and the item count (router_escalate_items) are
; configuration; see config/config.yaml.

; Declared before use so that the calls below compile as calls; configure adds the
; configured value when the plugin loads (the idiom of src/loop.metta).
(= (premium_model) (empty))
(= (router_escalate_items) (empty))

; Create term atoms for fast access. Note a sequence number is attached for reference.
(= (create_temp_atoms $prompt_list $seq_number)
   (if (== $prompt_list ())
      True
      (let*
        (
        ($atom (car-atom $prompt_list))
        ($next_number (+ $seq_number 1))
        ($_ (add-atom &temp (prompt_atom $atom $next_number)))
        ($_ (log INFO "atom>" ($atom $next_number)))
        )
        (create_temp_atoms (cdr-atom $prompt_list) $next_number))))

(= (lookup_term $term)
    (match &temp (prompt_atom $atom $_) 
                        (if (== $atom $term)
                           $atom
                           (empty))))

; &temp is one global space, and delete_temp_atoms removes every prompt_atom in it:
; harmless while one decision runs at a time, wrong once two can overlap (a retry
; loop, an out-of-process router).
(= (delete_temp_atoms)
   (collapse (match &temp (prompt_atom $x $seq) (remove-atom &temp (prompt_atom $x $seq)))))

; Look for a variety of common situations signalling the need for a premium model call.
; Return the configured model's catalogue entry, or premium_model on the same provider.
; Note:  The prompt is a subset of the request -- the tool call results and user
;     messages, normalised.
(= (default_router $request $catalogue $last_outcome)
   (default_router_text (llmRequestContentsNormalized $request) $catalogue))

(= (default_router_text $prompt $catalogue)
   (let* (
         ; create a list of terms, type string, using native Prolog from the single prompt string.
         ($prompt_list (split_string $prompt " " " "))
         ($_ (create_temp_atoms $prompt_list 0))
         ; look for simple terms hinting at complexity; the keywords come from Python
         ; as symbols and the terms are strings, so each keyword is compared by repr.
         ($keywords (get-state &defaultRouterKeywords))
         ($found_complexity_term
               (collapse (lookup_term (repr (superpose $keywords)))))
         ; Create list to count the total number of tool results and user messages 
         ($number_of_issues (collapse (match &temp (prompt_atom $atom $seq) 
                              (if (or (== $atom "role_user") (== $atom "role_tool")) 
                                    $seq
                                    (empty))))) 
         ; cleanup
         ($_ (delete_temp_atoms))
         ($economy (car-atom $catalogue))
         ($provider (car-atom $economy))
         )
         (if (and (== $found_complexity_term ())
                  (< (size-atom $number_of_issues) (router_escalate_items)))
                           $economy
                           ($provider (premium_model)))))

; The keywords are normalised once, with the text's own function, and logged by it.
(= (loadOmegaPlugin)
   (progn
     (configure premium_model "")
     (configure router_escalate_items 9)
     (change-state! &defaultRouterKeywords
       (llmKeywordsNormalized (configGetByKey router_escalate_keywords "alert_failed,error,premium_model")))
     (registerLLMRouter "default" default_router)))
