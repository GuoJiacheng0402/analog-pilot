;; ===========================================================================
;;  AnalogPilot SKILL bridge
;; ===========================================================================
;;  Load this in the Virtuoso CIW (the `apilot start` command generates an
;;  apilot_setup.il that sets ApDaemon/ApPort and then loads this file).
;;
;;  Mechanism (Cadence's public SKILL IPC facility):
;;    * ipcBeginProcess() launches a Python daemon as a child of this Virtuoso
;;      process. The daemon binds a loopback-only TCP socket.
;;    * The local `apilot` client connects to that socket through an SSH tunnel
;;      and sends a SKILL expression.
;;    * The daemon forwards the expression on its stdout; Cadence delivers it to
;;      ApOnData below, which evalstring()s it in this Virtuoso process.
;;    * The framed result is written back to the daemon's stdin via
;;      ipcWriteProcess(), and the daemon returns it to the client over TCP.
;;
;;  Reply framing (this process -> daemon stdin):  \001 <STATUS> \002 <payload> \003
;;    <STATUS> is "OK" or "ERR".
;;
;;  Note: each socket request carries exactly one SKILL expression (one write /
;;  flush from the daemon). For large multi-line SKILL, upload it to a file and
;;  send a single  load("/path/to/file.il")  expression instead.
;; ===========================================================================

(let ()
  (unless (boundp 'ApPython) (setq ApPython "python3"))
  (unless (boundp 'ApDaemon) (setq ApDaemon "REPLACE_DAEMON_PATH"))
  (unless (boundp 'ApHost)   (setq ApHost   "127.0.0.1"))
  (unless (boundp 'ApPort)   (setq ApPort   0))

  ;; Frame: SOH(1) <STATUS> STX(2) <payload> ETX(3).  SKILL's sprintf "%c" does
  ;; NOT turn an integer into a control byte, so build the bytes with intToChar.
  (defun ApReply (ipcId status payload)
    (ipcWriteProcess ipcId
      (strcat (intToChar 1) status (intToChar 2) (sprintf nil "%L" payload) (intToChar 3))))

  (defun ApOnData (ipcId data)
    (let (res)
      (if (errset (setq res (evalstring data)) t)
          (ApReply ipcId "OK" res)
          (ApReply ipcId "ERR" errset.errset))))

  ;; Daemon stderr (e.g. its startup banner). Just observe it; do NOT write back
  ;; to the daemon here, or the stray frame would desync the first real command.
  (defun ApOnErr (ipcId data) data)
  (defun ApOnExit (ipcId status) (printf "[apilot] daemon exited (%L)\n" status))

  ;; Launch the daemon with a clean library environment:
  ;;   /usr/bin/env -u LD_LIBRARY_PATH -u LD_PRELOAD   -> Virtuoso inherits an
  ;;     LD_PRELOAD (old OpenSSL) / LD_LIBRARY_PATH that break the system python;
  ;;     unset them so python launches cleanly.
  ;;   stdbuf -oL  +  python -u                        -> unbuffered stdout so the
  ;;     daemon's writes reach Virtuoso immediately (required by the protocol).
  (setq ApIpc
    (ipcBeginProcess
      (sprintf nil "/usr/bin/env -u LD_LIBRARY_PATH -u LD_PRELOAD stdbuf -oL %s -u %s %s %d"
               ApPython ApDaemon ApHost ApPort)
      ""
      'ApOnData 'ApOnErr 'ApOnExit ""))

  (printf "[apilot] bridge ready: bind=%s:%d daemon=%s\n" ApHost ApPort ApDaemon)
)
