; Routers (ADR-0001). A router is a MeTTa function
;   (router $request $catalogue $last_outcome) -> (provider model)
; registered by name from its plugin's loadOmegaPlugin, through
; config/plugins.yaml. $last_outcome is () until increment 4. The name goes
; through Python both when registered and when looked up, so the two compare.

(: registerLLMRouter (-> Atom Atom Expression))
(= (registerLLMRouter $name $function)
   (let $id (py-call (providers.registerLLMRouter $name))
     (progn
       (add-atom &self (llmRouter $id $function))
       ())))

; Routing off is a configuration: the null router, under the empty name.
(= (llmNullRouter $request $catalogue $last_outcome)
   (py-call (providers.llmNullRouter $request)))

!(registerLLMRouter "" llmNullRouter)

; Resolve the configured router once; an unregistered name raises and halts.
(= (llmRouterStart $router)
   (let $id (py-call (providers.llmRouterStart $router))
     (change-state! &llmRouter (match &self (llmRouter $id $function) $function))))

(= (llmProviderStart $provider)
   (py-call (providers.llmProviderStart $provider)))

; The hook: every request goes through the router, then the catalogue.
(= (llmProviderChat $request $router)
   (let $answer (catch (let $function (get-state &llmRouter)
                         ($function $request (py-call (providers.llmCatalogueGet)) ())))
     (case $answer
       (((Error $call $message) (py-call (providers.llmRouterRaised $router (swrite $answer))))
        ($value (py-call (providers.llmProviderChatRouted $request $router $value)))))))

; For routers, which make no py-call (R2 check 1): the request's text and the
; configured keywords, normalised by the same function.
(= (llmRequestContentsNormalized $request)
   (py-call (providers.llmRequestContentsNormalized $request)))

(= (llmKeywordsNormalized $keywords)
   (py-call (providers.llmKeywordsNormalized $keywords)))

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
