"""Start the demo with an explicit AI provider. Does not call an AI model."""
import argparse
import os
import ai_backends


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',required=True,choices=ai_backends.PROVIDERS)
    parser.add_argument('--model',default=None)
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    settings=ai_backends.Settings(args.provider,args.model if args.model is not None else os.environ.get('AI_MODEL',''))
    try:
        ai_backends.validate_setup(settings,authenticate=True)
    except ai_backends.AIError as exc:
        parser.error(str(exc))
    os.environ['AI_PROVIDER']=settings.provider
    os.environ['AI_MODEL']=settings.model
    print(f"Starting with {settings.public()['label']} / {settings.public()['effective_model']}")
    import uvicorn
    uvicorn.run('app:app',host=args.host,port=args.port)


if __name__=='__main__': main()
