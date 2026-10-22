; Return the selected provider and model, with role metadata for credentials
; and debug accounting when two roles name the same provider/model.
!(import! &self (library Omega ./src/router_policy.py))

(= (default_router $request $catalogue $last_outcome)
   (let $role (if (py-call (router_policy.needs_premium $request $last_outcome))
                 "premium"
                 "routine")
     (py-call (router_policy.catalog_selection $catalogue $role))))

(= (loadOmegaPlugin)
   (registerLLMRouter "default" default_router))
