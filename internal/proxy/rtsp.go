package proxy

import (
	"context"
	"io"
	"log"
	"net"
	"sync"
)

func StartRTSP(ctx context.Context, localAddr, remoteAddr string) error {
	listener, err := net.Listen("tcp", localAddr)
	if err != nil {
		return err
	}

	log.Printf("RTSP proxy %s -> %s", localAddr, remoteAddr)

	go func() {
		<-ctx.Done()
		listener.Close()
	}()

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				log.Printf("RTSP accept error: %v", err)
				continue
			}
			go handleConn(conn, remoteAddr)
		}
	}()

	return nil
}

func handleConn(client net.Conn, remoteAddr string) {
	defer client.Close()

	remote, err := net.Dial("tcp", remoteAddr)
	if err != nil {
		log.Printf("RTSP proxy: failed to connect to %s: %v", remoteAddr, err)
		return
	}
	defer remote.Close()

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		io.Copy(remote, client)
	}()
	go func() {
		defer wg.Done()
		io.Copy(client, remote)
	}()

	wg.Wait()
}
