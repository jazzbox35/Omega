(= (create_temp_atoms $prompt_list)
   (if (== $prompt_list ())
       True
       (progn (add-atom &temp (prompt_atom (car-atom $prompt_list)))
              (create_temp_atoms (cdr-atom $prompt_list)))))

(= (delete_temp_atoms)
   (collapse (match &temp (prompt_atom $x) (remove-atom &temp (prompt_atom $x)))))

(= (lookup_term $term)
   (match &temp (prompt_atom $atom)
          (if (== $atom $term) 1 (empty))))

; Route on exact space-separated tokens, as in the original default router.
(= (default_router $prompt $max_tokens $reasoning_mode)
   (let* (($prompt_list (split_string $prompt " " " "))
          ($_ (create_temp_atoms $prompt_list))
          ($found_complexity
             (collapse (lookup_term (superpose ("ALERT_FAILED" "premium_model")))))
          ($_ (delete_temp_atoms)))
         (if (== $found_complexity ()) economy_model premium_model)))

; Read message contents directly through the Python bridge; keep the request intact.
(= (llmRequestRoutingText $request)
   (atomic_list_concat
      (collapse
         (let $message (superpose (py-call (builtins.getattr $request "messages")))
              (py-call (builtins.str (py-call (builtins.getattr $message "content"))))))
      " "))

(= (llmProviderStart $provider)
   (py-call (providers.llmProviderStart $provider)))

(= (llmProviderChat $request)
     (py-call (providers.llmProviderChat $request)))

(= (llmProviderChat $request $router)
   (case $router
      ((default
         (let $tier (default_router
                       (llmRequestRoutingText $request)
                       (py-call (builtins.getattr $request "max_tokens"))
                       (py-call (builtins.getattr $request "reasoning_mode")))
              (py-call (providers.llmProviderChat $request $tier))))
       ($_otherwise (llmProviderChat $request)))))

(= (llmRequestMessage role $role content $content)
   (py-call (providers.llmRequestMessage $role $content)))

(= (llmToolCallResponseMessage role $role callid $callid content $content)
   (py-call (providers.llmToolCallResponseMessage $role $callid $content)))

(= (llmToolCallMessage role $role calls $calls content $content)
   (py-call (providers.llmToolCallMessage $role $calls $content)))

(= (llmRequest $prompt $episodes $max_tokens $reasoning_mode $tools)
   (py-call (providers.llmRequest $prompt $episodes $max_tokens $reasoning_mode $tools)))

(= (llmResponseIsEmpty $response)
   (py-call (providers.llmResponseIsEmpty $response)))

(= (llmResponseCalls $response)
   (py-call (providers.llmResponseCalls $response)))

(= (llmToolCallGetName $call)
   (py-call (providers.llmToolCallGetName $call)))

(= (llmToolCallGetId $call)
   (py-call (providers.llmToolCallGetId $call)))

(= (llmToolCallGetArguments $call)
   (py-str ((py-call (providers.llmToolCallGetArguments $call)))))

(= (llmToolCallIsError $call)
   (py-call (providers.llmToolCallIsError $call)))

(= (llmToolCallGetError $call)
   (py-call (providers.llmToolCallGetError $call)))

(= (llmResponseToSExpr $call)
   (py-call (providers.llmResponseToSExpr $call)))
