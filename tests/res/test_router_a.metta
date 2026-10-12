(= (test_router_a $request $catalogue $last_outcome) ("Test" "a"))

(= (loadOmegaPlugin)
   (registerLLMRouter "test_router_a" test_router_a))
