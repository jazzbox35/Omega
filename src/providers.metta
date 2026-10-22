(: registerLLMRouter (-> Atom Atom Expression))
(= (registerLLMRouter $name $function)
   (let $id (py-call (providers.registerLLMRouter $name))
     (progn
       (add-atom &self (llmRouter $id $function))
       ())))

(= (llmRouterStart)
   (let $id (py-call (providers.llmRouterStart))
     (if (py-call (providers.llmRoutingEnabled))
         (change-state! &llmRouter
           (match &self (llmRouter $id $function) $function))
         ())))

(= (llmProviderStart $provider)
   (progn
     (py-call (providers.llmProviderStart $provider))
     (llmRouterStart)))

(= (llmProviderChat $request)
   (if (py-call (providers.llmRoutingEnabled))
       (let $answer (catch
                      (let $function (get-state &llmRouter)
                        ($function $request
                          (py-call (providers.llmCatalogueGet))
                          (py-call (providers.llmLastOutcome)))))
         (case $answer
           (((Error $call $message)
             (py-call (providers.llmRouterRaised (swrite $answer))))
            ($selection (py-call (providers.llmProviderChatRouted $request $selection))))))
       (py-call (providers.llmProviderChat $request))))

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
