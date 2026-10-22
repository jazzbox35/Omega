;configured at runtime:
(= (commchannel) (empty))

;Connect all the channels:
(= (initChannels)
   (progn (log INFO "channels" "Initializing channels")
          (configure commchannel irc)
          (commChannelStart (commchannel))))

(= (commChannelStart $commchannel)
   (py-call (channels.commChannelStart $commchannel)))

(= (commChannelReceive)
   (py-call (channels.commChannelReceive)))

(= (commChannelSend $message)
   (py-call (channels.commChannelSend $message)))

;Receive the latest user message considering all communication channels:
(= (receive)
   (commChannelReceive))

;Send a message to all communication channels:
!(change-state! &lastsend "")
(= (send $msg)
   (if (!= $msg (get-state &lastsend))
       (progn (change-state! &lastsend $msg)
              ; BEGIN DEBUG: append cumulative calls per router role to send.
              (let $debugmsg (py-call (providers.debugRouterCallTotals $msg))
              ; END DEBUG
              (let $safemsg (string-replace $debugmsg  "\n" "\\n")
                   (let $temp (cut) (commChannelSend $safemsg))))) _))
